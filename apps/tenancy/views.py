from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import role_required
from apps.accounts.forms import AccountFields
from apps.accounts.models import Role, User
from apps.accounts.views import _open_invitation, create_user_invitation
from apps.audit.services import record, snapshot
from apps.core.emails import send_invitation_email
from apps.core.tokens import invitation_expiry, new_token
from . import access
from .forms import ClientCreateForm, ClientCompanyForm, FactoryForm, LegalEntityForm, SupplierForm, SupplierInviteForm
from .models import LinkStatus, SupplierClientLink, SupplierInvitation, SupplierStatus


# ---------------------------------------------------------------- clients
@role_required(Role.SZ_ADMIN)
def client_list(request):
    q = request.GET.get("q", "").strip()
    clients = access.visible_clients(request.user)
    if q:
        clients = clients.filter(name__icontains=q)
    from django.db.models import Count
    clients = clients.annotate(n_entities=Count("entities", distinct=True),
                               n_suppliers=Count("supplier_links", distinct=True))
    return render(request, "tenancy/client_list.html", {"clients": clients, "q": q})


@role_required(Role.SZ_ADMIN)
@require_http_methods(["GET", "POST"])
def client_create(request):
    form = ClientCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            client = form.save(commit=False)
            client.created_by = request.user
            client.save()
            record(request, "client.created", client, after=snapshot(client), client=client)
            link = None
            if form.cleaned_data.get("admin_email"):
                _, link = create_user_invitation(request, email=form.cleaned_data["admin_email"],
                                                 role=Role.CLIENT_ADMIN, client=client)
        messages.success(request, f"{client.name} created.")
        if link:
            return render(request, "includes/invite_link.html", {
                "link": link, "email": form.cleaned_data["admin_email"],
                "back": reverse("tenancy:client_detail", args=[client.pk])})
        return redirect("tenancy:client_detail", pk=client.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Create client company",
                                                 "submit": "Create client", "cancel": reverse("tenancy:client_list")})


@login_required
def my_client(request):
    if not request.user.is_client_user:
        raise PermissionDenied
    return redirect("tenancy:client_detail", pk=request.user.client_company_id)


@login_required
def client_detail(request, pk):
    if request.user.is_supplier_user:
        raise PermissionDenied
    client = get_object_or_404(access.visible_clients(request.user), pk=pk)
    can_manage = access.can_manage_client(request.user, client)
    ctx = {
        "client": client, "can_manage": can_manage,
        "entities": access.visible_entities(request.user).filter(client=client),
        "links": access.visible_links(request.user).filter(client=client).prefetch_related("entities"),
        "invitations": client.supplier_invitations.prefetch_related("entities") if can_manage else [],
        "users": User.objects.filter(client_company=client) if can_manage else [],
    }
    return render(request, "tenancy/client_detail.html", ctx)


@role_required(Role.SZ_ADMIN, Role.CLIENT_ADMIN)
@require_http_methods(["GET", "POST"])
def client_edit(request, pk):
    client = get_object_or_404(access.visible_clients(request.user), pk=pk)
    before = snapshot(client)
    form = ClientCompanyForm(request.POST or None, instance=client)
    if not request.user.is_sz_admin:
        form.fields.pop("status")
    if request.method == "POST" and form.is_valid():
        form.save()
        record(request, "client.updated", client, before=before, after=snapshot(client), client=client)
        messages.success(request, "Company details saved.")
        return redirect("tenancy:client_detail", pk=pk)
    return render(request, "generic/form.html", {"form": form, "title": f"Edit {client.name}", "submit": "Save",
                                                 "cancel": reverse("tenancy:client_detail", args=[pk])})


# ---------------------------------------------------------------- entities
@role_required(Role.SZ_ADMIN, Role.CLIENT_ADMIN)
@require_http_methods(["GET", "POST"])
def entity_create(request, client_pk):
    client = get_object_or_404(access.visible_clients(request.user), pk=client_pk)
    form = LegalEntityForm(request.POST or None, client=client)
    if request.method == "POST" and form.is_valid():
        entity = form.save(commit=False)
        entity.client = client
        entity.save()
        record(request, "entity.created", entity, after=snapshot(entity))
        messages.success(request, f"{entity.name} added.")
        return redirect("tenancy:client_detail", pk=client.pk)
    return render(request, "generic/form.html", {"form": form, "title": f"Add legal entity to {client.name}",
                                                 "submit": "Add entity",
                                                 "cancel": reverse("tenancy:client_detail", args=[client.pk])})


@login_required
def entity_detail(request, pk):
    if request.user.is_supplier_user:
        raise PermissionDenied
    entity = get_object_or_404(access.visible_entities(request.user).select_related("client"), pk=pk)
    links = access.visible_links(request.user).filter(entities=entity)
    return render(request, "tenancy/entity_detail.html", {
        "entity": entity, "links": links, "can_manage": access.can_manage_client(request.user, entity.client)})


@role_required(Role.SZ_ADMIN, Role.CLIENT_ADMIN)
@require_http_methods(["GET", "POST"])
def entity_edit(request, pk):
    entity = get_object_or_404(access.visible_entities(request.user).select_related("client"), pk=pk)
    before = snapshot(entity)
    form = LegalEntityForm(request.POST or None, instance=entity, client=entity.client)
    if request.method == "POST" and form.is_valid():
        form.save()
        record(request, "entity.updated", entity, before=before, after=snapshot(entity))
        messages.success(request, "Entity saved.")
        return redirect("tenancy:entity_detail", pk=pk)
    return render(request, "generic/form.html", {"form": form, "title": f"Edit {entity.name}", "submit": "Save",
                                                 "cancel": reverse("tenancy:entity_detail", args=[pk])})


# ---------------------------------------------------------------- supplier invitations
@role_required(Role.SZ_ADMIN, Role.CLIENT_ADMIN)
@require_http_methods(["GET", "POST"])
def supplier_invite(request, client_pk):
    client = get_object_or_404(access.visible_clients(request.user), pk=client_pk)
    form = SupplierInviteForm(request.POST or None, client=client)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        raw, digest = new_token()
        inv = SupplierInvitation.objects.create(client=client, supplier_name=d["supplier_name"], email=d["email"].lower(),
                                                message=d["message"], token_hash=digest,
                                                expires_at=invitation_expiry(), invited_by=request.user)
        inv.entities.set(d["entities"])
        link = request.build_absolute_uri(reverse("tenancy:supplier_accept", args=[raw]))
        intro = (f"{client.name} uses SustainZone EUDR Gateway to collect EU Deforestation Regulation (EUDR) "
                 f"information from its suppliers. You have been invited to register {d['supplier_name']}. "
                 "You only need to register your company once.")
        if d["message"]:
            intro += f"\n\nMessage from {client.name}:\n{d['message']}"
        send_invitation_email(inv.email, f"{client.name}: please register on SustainZone EUDR Gateway", intro, link)
        record(request, "supplier_invitation.created", inv, after=snapshot(inv), client=client)
        return render(request, "includes/invite_link.html", {
            "link": link, "email": inv.email, "back": reverse("tenancy:client_detail", args=[client.pk])})
    return render(request, "generic/form.html", {"form": form, "title": f"Invite a supplier to {client.name}",
                                                 "submit": "Send invitation",
                                                 "cancel": reverse("tenancy:client_detail", args=[client.pk])})


@role_required(Role.SZ_ADMIN, Role.CLIENT_ADMIN)
@require_http_methods(["POST"])
def supplier_invite_revoke(request, pk):
    inv = get_object_or_404(SupplierInvitation.objects.filter(client__in=access.visible_clients(request.user)),
                            pk=pk, accepted_at__isnull=True, revoked_at__isnull=True)
    inv.revoked_at = timezone.now()
    inv.save(update_fields=["revoked_at"])
    record(request, "supplier_invitation.revoked", inv, client=inv.client)
    messages.success(request, "Invitation revoked.")
    return redirect("tenancy:client_detail", pk=inv.client_id)


def _link_supplier(request, inv, supplier):
    link, created = SupplierClientLink.objects.get_or_create(
        supplier=supplier, client=inv.client, defaults={"invited_by": inv.invited_by, "status": LinkStatus.ACTIVE})
    link.entities.add(*inv.entities.all())
    inv.accepted_at, inv.accepted_supplier = timezone.now(), supplier
    inv.save(update_fields=["accepted_at", "accepted_supplier"])
    record(request, "supplier_link.created" if created else "supplier_link.updated", link,
           after=snapshot(link), client=inv.client, supplier=supplier)
    return link


@require_http_methods(["GET", "POST"])
def supplier_accept(request, token):
    inv = _open_invitation(SupplierInvitation, token)
    if inv is None:
        return render(request, "accounts/invite_invalid.html", status=404)

    # Existing supplier accepting a new client relationship (register once, many clients)
    if request.user.is_authenticated:
        if request.user.role != Role.SUPPLIER_ADMIN:
            return render(request, "accounts/invite_logged_in.html")
        if request.method == "POST":
            with transaction.atomic():
                inv = SupplierInvitation.objects.select_for_update().get(pk=inv.pk)
                if inv.accepted_at:
                    return render(request, "accounts/invite_invalid.html", status=404)
                _link_supplier(request, inv, request.user.supplier)
            messages.success(request, f"{request.user.supplier.name} is now connected to {inv.client.name}.")
            return redirect("core:dashboard")
        return render(request, "tenancy/supplier_accept_existing.html", {"inv": inv})

    company_form = SupplierForm(request.POST or None, prefix="company",
                                initial={"name": inv.supplier_name, "contact_email": inv.email})
    account_form = AccountFields(request.POST or None, prefix="account", initial={"email": inv.email})
    if request.method == "POST" and company_form.is_valid() and account_form.is_valid():
        a = account_form.cleaned_data
        with transaction.atomic():
            inv = SupplierInvitation.objects.select_for_update().get(pk=inv.pk)
            if inv.accepted_at:
                return render(request, "accounts/invite_invalid.html", status=404)
            supplier = company_form.save(commit=False)
            supplier.status = SupplierStatus.ACTIVE
            supplier.save()
            user = User.objects.create_user(a["email"], a["password1"], full_name=a["full_name"],
                                            role=Role.SUPPLIER_ADMIN, supplier=supplier)
            record(request, "supplier.registered", supplier, after=snapshot(supplier), client=inv.client, supplier=supplier)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            _link_supplier(request, inv, supplier)
        messages.success(request, "Registration complete. Next, add the products you supply.")
        return redirect("core:dashboard")
    return render(request, "tenancy/supplier_register.html",
                  {"inv": inv, "company_form": company_form, "account_form": account_form, "token": token})


# ---------------------------------------------------------------- suppliers
@login_required
def supplier_list(request):
    if request.user.is_supplier_user:
        return redirect("tenancy:my_supplier")
    links = access.visible_links(request.user).prefetch_related("entities").order_by("supplier__name")
    q = request.GET.get("q", "").strip()
    if q:
        links = links.filter(supplier__name__icontains=q)
    return render(request, "tenancy/supplier_list.html", {"links": links, "q": q})


@login_required
def supplier_detail(request, pk):
    supplier = get_object_or_404(access.visible_suppliers(request.user), pk=pk)
    ctx = {
        "supplier": supplier,
        "links": access.visible_links(request.user).filter(supplier=supplier).prefetch_related("entities"),
        "products": access.visible_products(request.user).filter(supplier=supplier),
        "plots": access.visible_plots(request.user).filter(supplier=supplier).select_related("producer"),
        "producers": access.visible_producers(request.user).filter(suppliers=supplier),
        "factories": supplier.factories.all(),
        "is_own": request.user.supplier_id == supplier.pk,
    }
    return render(request, "tenancy/supplier_detail.html", ctx)


@login_required
def my_supplier(request):
    if not request.user.is_supplier_user:
        raise PermissionDenied
    return supplier_detail(request, request.user.supplier_id)


@role_required(Role.SUPPLIER_ADMIN)
@require_http_methods(["GET", "POST"])
def my_supplier_edit(request):
    supplier = request.user.supplier
    before = snapshot(supplier)
    form = SupplierForm(request.POST or None, instance=supplier)
    if request.method == "POST" and form.is_valid():
        form.save()
        record(request, "supplier.updated", supplier, before=before, after=snapshot(supplier))
        messages.success(request, "Company profile saved.")
        return redirect("tenancy:my_supplier")
    return render(request, "generic/form.html", {"form": form, "title": "Edit company profile", "submit": "Save",
                                                 "cancel": reverse("tenancy:my_supplier")})


@role_required(Role.SUPPLIER_ADMIN)
@require_http_methods(["GET", "POST"])
def factory_create(request):
    form = FactoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        f = form.save(commit=False)
        f.supplier = request.user.supplier
        f.save()
        record(request, "factory.created", f, after=snapshot(f))
        messages.success(request, "Factory added.")
        return redirect("tenancy:my_supplier")
    return render(request, "generic/form.html", {"form": form, "title": "Add factory", "submit": "Add factory",
                                                 "cancel": reverse("tenancy:my_supplier")})
