"""Tenant and object-level isolation that the journey test does not cover."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
import tempfile

from apps.accounts.models import Role, User
from apps.supply.geo import parse_geojson
from apps.supply.models import Evidence, Producer, Product, SourcePlot
from apps.tenancy.models import ClientCompany, LegalEntity, Supplier, SupplierClientLink
from .helpers import PASSWORD, fc_json

TMP_MEDIA = tempfile.mkdtemp()


def make_client(name):
    return ClientCompany.objects.create(name=name, country="DE", address="x", main_contact_name="m",
                                        main_contact_email=f"m@{name}.example")


def make_supplier(name, *clients):
    s = Supplier.objects.create(name=name, country="PL", address="x", contact_name="c", contact_email=f"c@{name}.example")
    for c in clients:
        SupplierClientLink.objects.create(supplier=s, client=c)
    return s


def make_plot(supplier, clients, name="Plot"):
    g = parse_geojson(fc_json())
    p = SourcePlot.objects.create(supplier=supplier, name=name, country="PL", geometry=g["geometry"], area_ha=g["area_ha"])
    p.clients.set(clients)
    return p


@override_settings(MEDIA_ROOT=TMP_MEDIA, PRIVATE_MEDIA_ROOT=TMP_MEDIA)
class IsolationTest(TestCase):
    def setUp(self):
        self.c1, self.c2 = make_client("clientone"), make_client("clienttwo")
        self.shared_supplier = make_supplier("shared", self.c1, self.c2)
        self.supplier_b = make_supplier("supplierb", self.c1)
        self.e1a = LegalEntity.objects.create(client=self.c1, name="E1A", country="DE", address="x")
        self.e1b = LegalEntity.objects.create(client=self.c1, name="E1B", country="FR", address="x")
        SupplierClientLink.objects.get(supplier=self.shared_supplier, client=self.c1).entities.add(self.e1a)
        SupplierClientLink.objects.get(supplier=self.supplier_b, client=self.c1).entities.add(self.e1b)
        mk = lambda email, **kw: User.objects.create_user(email, PASSWORD, full_name=email, **kw)
        self.c1_admin = mk("a@c1.example", role=Role.CLIENT_ADMIN, client_company=self.c1)
        self.c2_admin = mk("a@c2.example", role=Role.CLIENT_ADMIN, client_company=self.c2)
        self.c1_entity_user = mk("e@c1.example", role=Role.CLIENT_ENTITY_USER, client_company=self.c1)
        self.c1_entity_user.permitted_entities.add(self.e1a)
        self.shared_admin = mk("a@shared.example", role=Role.SUPPLIER_ADMIN, supplier=self.shared_supplier)
        self.shared_user = mk("u@shared.example", role=Role.SUPPLIER_USER, supplier=self.shared_supplier)
        self.b_admin = mk("a@b.example", role=Role.SUPPLIER_ADMIN, supplier=self.supplier_b)
        # shared supplier shares plot1 only with client 1, plot2 with both
        self.plot_c1_only = make_plot(self.shared_supplier, [self.c1], "Only for C1")
        self.plot_both = make_plot(self.shared_supplier, [self.c1, self.c2], "For both")
        self.plot_b = make_plot(self.supplier_b, [self.c1], "Supplier B plot")

    def get(self, user, name, *args):
        self.client.force_login(user)
        return self.client.get(reverse(name, args=args))

    def test_supplier_shares_per_client(self):
        self.assertEqual(self.get(self.c2_admin, "supply:plot_detail", self.plot_c1_only.pk).status_code, 404)
        self.assertEqual(self.get(self.c2_admin, "supply:plot_detail", self.plot_both.pk).status_code, 200)
        self.assertEqual(self.get(self.c1_admin, "supply:plot_detail", self.plot_c1_only.pk).status_code, 200)

    def test_supplier_cannot_see_other_supplier(self):
        self.assertEqual(self.get(self.b_admin, "supply:plot_detail", self.plot_both.pk).status_code, 404)
        self.assertEqual(self.get(self.b_admin, "tenancy:supplier_detail", self.shared_supplier.pk).status_code, 404)
        self.assertEqual(self.get(self.b_admin, "supply:plot_edit", self.plot_both.pk).status_code, 404)
        self.assertNotContains(self.get(self.b_admin, "supply:plot_list"), "For both")

    def test_entity_user_limited_to_permitted_entities(self):
        self.assertEqual(self.get(self.c1_entity_user, "tenancy:supplier_detail", self.shared_supplier.pk).status_code, 200)
        self.assertEqual(self.get(self.c1_entity_user, "tenancy:supplier_detail", self.supplier_b.pk).status_code, 404)
        self.assertEqual(self.get(self.c1_entity_user, "supply:plot_detail", self.plot_b.pk).status_code, 404)
        self.assertEqual(self.get(self.c1_entity_user, "tenancy:entity_detail", self.e1b.pk).status_code, 404)
        self.assertEqual(self.get(self.c1_entity_user, "tenancy:entity_create", self.c1.pk).status_code, 403)

    def test_supplier_user_cannot_register_products(self):
        self.assertEqual(self.get(self.shared_user, "supply:product_create").status_code, 403)
        self.assertEqual(self.get(self.shared_user, "supply:plot_create").status_code, 403)

    def test_supplier_cannot_access_client_pages(self):
        self.assertEqual(self.get(self.shared_admin, "tenancy:client_detail", self.c1.pk).status_code, 403)
        self.assertEqual(self.get(self.shared_admin, "tenancy:client_create").status_code, 403)

    def test_form_cannot_share_with_unlinked_client_or_foreign_producer(self):
        c3 = make_client("clientthree")
        foreign_producer = Producer.objects.create(name="Foreign", country="BR", created_by_supplier=self.supplier_b)
        foreign_producer.suppliers.add(self.supplier_b)
        self.client.force_login(self.shared_admin)
        r = self.client.post(reverse("supply:product_create"), {"name": "X", "commodity": "wood", "unit": "kg",
                                                                  "clients": [c3.pk], "producers": [foreign_producer.pk]})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Product.objects.filter(name="X").exists())
        self.assertIn("clients", r.context["form"].errors)
        self.assertIn("producers", r.context["form"].errors)

    def test_evidence_download_permissions(self):
        self.client.force_login(self.shared_admin)
        f = SimpleUploadedFile("permit.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.client.post(reverse("supply:evidence_upload", args=["source_plot", self.plot_c1_only.pk]),
                             {"file": f, "category": "legality"})
        self.assertEqual(r.status_code, 302)
        ev = Evidence.objects.get()
        url = reverse("supply:evidence_download", args=[ev.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        for user, expected in ((self.c1_admin, 200), (self.c2_admin, 404), (self.b_admin, 404)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, expected, user.email)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)  # to login

    def test_evidence_rejects_disguised_file(self):
        self.client.force_login(self.shared_admin)
        f = SimpleUploadedFile("permit.pdf", b"MZ\x90\x00 not a pdf", content_type="application/pdf")
        r = self.client.post(reverse("supply:evidence_upload", args=["source_plot", self.plot_c1_only.pk]),
                             {"file": f, "category": "legality"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Evidence.objects.exists())

    def test_expired_and_revoked_invites_rejected(self):
        from apps.core.tokens import new_token
        from apps.tenancy.models import SupplierInvitation
        raw, digest = new_token()
        inv = SupplierInvitation.objects.create(client=self.c1, supplier_name="late", email="l@l.example",
                                                token_hash=digest, expires_at=timezone.now(), invited_by=self.c1_admin)
        self.assertEqual(self.client.get(reverse("tenancy:supplier_accept", args=[raw])).status_code, 404)
        self.assertEqual(self.client.get(reverse("tenancy:supplier_accept", args=["garbage"])).status_code, 404)

    def test_existing_supplier_links_to_new_client_without_reregistering(self):
        from apps.core.tokens import invitation_expiry, new_token
        from apps.tenancy.models import SupplierInvitation
        raw, digest = new_token()
        SupplierInvitation.objects.create(client=self.c2, supplier_name="B", email="a@b.example", token_hash=digest,
                                          expires_at=invitation_expiry(), invited_by=self.c2_admin)
        self.client.force_login(self.b_admin)
        r = self.client.post(reverse("tenancy:supplier_accept", args=[raw]))
        self.assertRedirects(r, reverse("core:dashboard"))
        self.assertTrue(SupplierClientLink.objects.filter(supplier=self.supplier_b, client=self.c2).exists())
        self.assertEqual(Supplier.objects.filter(name="supplierb").count(), 1)
        # linking alone shares nothing: C2 still cannot see Supplier B's plot
        self.assertEqual(self.get(self.c2_admin, "supply:plot_detail", self.plot_b.pk).status_code, 404)


class SecurityTest(TestCase):
    def test_login_rate_limited(self):
        User.objects.create_user("x@x.example", PASSWORD, full_name="X", role=Role.SZ_ADMIN)
        url = reverse("accounts:login")
        for _ in range(10):
            self.client.post(url, {"username": "x@x.example", "password": "wrong"})
        r = self.client.post(url, {"username": "x@x.example", "password": PASSWORD})
        self.assertEqual(r.status_code, 429)

    def test_passwords_hashed_with_argon2(self):
        u = User.objects.create_user("h@h.example", PASSWORD, full_name="H", role=Role.SZ_ADMIN)
        self.assertTrue(u.password.startswith("argon2"))

    def test_csrf_enforced(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        u = User.objects.create_user("s@s.example", PASSWORD, full_name="S", role=Role.SZ_ADMIN)
        c.force_login(u)
        self.assertEqual(c.post(reverse("tenancy:client_create"), {}).status_code, 403)

    def test_role_tenant_constraint(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            User.objects.create_user("bad@x.example", PASSWORD, full_name="B", role=Role.CLIENT_ADMIN)

    def test_security_headers(self):
        r = self.client.get(reverse("accounts:login"))
        self.assertIn("default-src 'self'", r["Content-Security-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")
