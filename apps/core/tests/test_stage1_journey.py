"""
Stage 1 acceptance test. Walks the full first journey through real HTTP views:

SustainZone Admin → Create Client → Create Entity → Invite Supplier → Supplier Registers
→ Add Product → Add Producer → Add Source Plot (polygon) → Map data reloads → Client views it
→ SustainZone sees everything → another client and another supplier cannot.
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.supply.models import Producer, Product, SourcePlot
from apps.tenancy.models import ClientCompany, LegalEntity, Supplier, SupplierClientLink
from .helpers import PASSWORD, POLYGON, account_payload, client_payload, entity_payload, fc_json, last_link, supplier_payload


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class Stage1JourneyTest(TestCase):
    def setUp(self):
        self.sz = User.objects.create_user("admin@sustainzone.example", PASSWORD, full_name="SZ Admin", role=Role.SZ_ADMIN)

    def login(self, email):
        self.client.logout()
        r = self.client.post(reverse("accounts:login"), {"username": email, "password": PASSWORD})
        self.assertEqual(r.status_code, 302, f"login failed for {email}")

    def create_client_with_admin(self, name, admin_email):
        self.login(self.sz.email)
        r = self.client.post(reverse("tenancy:client_create"), client_payload(name, admin_email=admin_email))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Invitation sent")
        client = ClientCompany.objects.get(name=name)
        link = last_link()
        self.client.logout()
        r = self.client.post(link, account_payload(admin_email, name=f"{name} Admin", prefix=""))
        self.assertRedirects(r, reverse("core:dashboard"))
        return client

    def test_full_stage1_journey_and_isolation(self):
        # 1–2. SZ admin logs in, creates client company, invites the client admin
        tsunami = self.create_client_with_admin("Tsunami Axis", "admin@tsunami.example")
        ta_admin = User.objects.get(email="admin@tsunami.example")
        self.assertEqual(ta_admin.role, Role.CLIENT_ADMIN)
        self.assertEqual(ta_admin.client_company, tsunami)

        # 3. Client legal entities (created by SZ admin and by the client admin)
        self.login(self.sz.email)
        r = self.client.post(reverse("tenancy:entity_create", args=[tsunami.pk]), entity_payload("Tsunami Axis Germany"))
        self.assertRedirects(r, reverse("tenancy:client_detail", args=[tsunami.pk]))
        self.login(ta_admin.email)
        self.client.post(reverse("tenancy:entity_create", args=[tsunami.pk]), entity_payload("Tsunami Axis France", "FR"))
        de = LegalEntity.objects.get(name="Tsunami Axis Germany")
        self.assertEqual(tsunami.entities.count(), 2)

        # 4. Client admin invites supplier for the German entity
        r = self.client.post(reverse("tenancy:supplier_invite", args=[tsunami.pk]),
                             {"supplier_name": "Supplier A Timber", "email": "anna@supplier-a.example", "entities": [de.pk]})
        self.assertContains(r, "Invitation sent")
        supplier_link = last_link()

        # 5. Supplier registers (anonymous), is logged in as Supplier Admin
        self.client.logout()
        self.assertContains(self.client.get(supplier_link), "Register Supplier A Timber")
        data = {**supplier_payload(), **account_payload("anna@supplier-a.example", "Anna Nowak")}
        r = self.client.post(supplier_link, data)
        self.assertRedirects(r, reverse("core:dashboard"))
        supplier = Supplier.objects.get(name="Supplier A Timber")
        anna = User.objects.get(email="anna@supplier-a.example")
        self.assertEqual((anna.role, anna.supplier), (Role.SUPPLIER_ADMIN, supplier))
        link = SupplierClientLink.objects.get(supplier=supplier, client=tsunami)
        self.assertEqual(list(link.entities.all()), [de])
        # invitation is single-use
        self.client.logout()
        self.assertEqual(self.client.get(supplier_link).status_code, 404)

        # 6. Supplier login
        self.login(anna.email)
        self.assertContains(self.client.get(reverse("core:dashboard")), "Getting started")

        # 8. Register producer
        r = self.client.post(reverse("supply:producer_create"),
                             {"name": "Lasy Wielkopolskie", "country": "PL", "address": "Forest road 3"})
        producer = Producer.objects.get(name="Lasy Wielkopolskie")
        self.assertRedirects(r, reverse("supply:producer_detail", args=[producer.pk]))

        # 7. Register product (shared with Tsunami Axis)
        r = self.client.post(reverse("supply:product_create"), {
            "name": "Sawn oak boards", "sku": "OAK-27", "commodity": "wood", "hs_code": "4407 91", "cn_code": "4407 91 15",
            "species_common": "European oak", "species_scientific": "Quercus robur", "producers": [producer.pk],
            "country_of_production": "PL", "unit": "m3", "clients": [tsunami.pk]})
        product = Product.objects.get(sku="OAK-27")
        self.assertRedirects(r, reverse("supply:product_detail", args=[product.pk]))
        self.assertEqual(product.cn_code, "44079115")

        # 9–12. Add source plot with polygon, stored in PostGIS with computed area
        r = self.client.post(reverse("supply:plot_create"), {
            "name": "Compartment 14B", "plot_reference": "PL-WLK-14B", "country": "PL", "producer": producer.pk,
            "products": [product.pk], "harvest_start": "2025-01-01", "harvest_end": "2025-03-31",
            "clients": [tsunami.pk], "geometry_geojson": fc_json(), "geometry_origin": "drawn"})
        plot = SourcePlot.objects.get(plot_reference="PL-WLK-14B")
        self.assertRedirects(r, reverse("supply:plot_detail", args=[plot.pk]))
        self.assertEqual(plot.geometry.geom_type, "MultiPolygon")
        self.assertEqual(plot.geometry.srid, 4326)
        self.assertTrue(Decimal("77.5") < plot.area_ha < Decimal("79"), plot.area_ha)  # ~700 m x 1113 m at 50.9°N (PostGIS geodesic: 78.20 ha)
        self.assertEqual(plot.geometry_source, "drawn")

        # 13. Reload: detail page embeds geometry for the map; edit form pre-populates it; GeoJSON endpoint works
        r = self.client.get(reverse("supply:plot_detail", args=[plot.pk]))
        self.assertContains(r, 'id="plot-map"')
        self.assertContains(r, '"MultiPolygon"')
        r = self.client.get(reverse("supply:plot_edit", args=[plot.pk]))
        self.assertContains(r, "MultiPolygon")
        gj = self.client.get(reverse("supply:plot_geojson", args=[plot.pk])).json()
        ring = gj["features"][0]["geometry"]["coordinates"][0][0]
        self.assertEqual(ring[0], POLYGON["features"][0]["geometry"]["coordinates"][0][0])

        # 14–16. Client admin sees supplier, product, source map
        self.login(ta_admin.email)
        self.assertContains(self.client.get(reverse("tenancy:supplier_list")), "Supplier A Timber")
        self.assertContains(self.client.get(reverse("tenancy:supplier_detail", args=[supplier.pk])), "Compartment 14B")
        self.assertContains(self.client.get(reverse("supply:product_detail", args=[product.pk])), "Quercus robur")
        self.assertContains(self.client.get(reverse("supply:plot_detail", args=[plot.pk])), "MultiPolygon")
        self.assertEqual(self.client.get(reverse("supply:plot_geojson", args=[plot.pk])).status_code, 200)
        # client cannot edit supplier data
        self.assertEqual(self.client.get(reverse("supply:plot_edit", args=[plot.pk])).status_code, 403)

        # 17. SustainZone sees everything
        self.login(self.sz.email)
        for url in (reverse("tenancy:client_detail", args=[tsunami.pk]), reverse("tenancy:supplier_detail", args=[supplier.pk]),
                    reverse("supply:product_detail", args=[product.pk]), reverse("supply:plot_detail", args=[plot.pk]),
                    reverse("supply:producer_detail", args=[producer.pk]), reverse("audit:list")):
            self.assertEqual(self.client.get(url).status_code, 200, url)

        # 18. Another client cannot see anything
        other = self.create_client_with_admin("Other Client GmbH", "admin@other.example")
        self.login("admin@other.example")
        for url in (reverse("tenancy:client_detail", args=[tsunami.pk]), reverse("tenancy:supplier_detail", args=[supplier.pk]),
                    reverse("supply:product_detail", args=[product.pk]), reverse("supply:plot_detail", args=[plot.pk]),
                    reverse("supply:plot_geojson", args=[plot.pk]), reverse("supply:producer_detail", args=[producer.pk]),
                    reverse("tenancy:entity_detail", args=[de.pk])):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertEqual(self.client.post(reverse("tenancy:entity_create", args=[tsunami.pk]),
                                          entity_payload("Hijack")).status_code, 404)
        self.assertEqual(self.client.post(reverse("tenancy:supplier_invite", args=[tsunami.pk]),
                                          {"supplier_name": "x", "email": "x@x.example"}).status_code, 404)
        for url in (reverse("tenancy:supplier_list"), reverse("supply:product_list"), reverse("supply:plot_list"),
                    reverse("core:dashboard")):
            r = self.client.get(url)
            self.assertNotContains(r, "Supplier A Timber")
            self.assertNotContains(r, "Compartment 14B")
            self.assertNotContains(r, "Sawn oak")
        self.assertFalse(AuditLog.objects.filter(client=other, object_type="supply.SourcePlot").exists())
        # client admins cannot list all clients
        self.assertEqual(self.client.get(reverse("tenancy:client_list")).status_code, 403)

        # Audit trail captured the journey
        actions = set(AuditLog.objects.values_list("action", flat=True))
        for a in ("client.created", "entity.created", "supplier_invitation.created", "supplier.registered",
                  "supplier_link.created", "producer.created", "product.created", "source_plot.created"):
            self.assertIn(a, actions)
