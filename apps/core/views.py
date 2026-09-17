from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render

from apps.audit.models import AuditLog
from apps.tenancy import access
from apps.tenancy.models import open_invitation_q, SupplierInvitation


@login_required
def dashboard(request):
    u = request.user
    ctx = {
        "n_suppliers": access.visible_suppliers(u).count(),
        "n_products": access.visible_products(u).count(),
        "n_producers": access.visible_producers(u).count(),
        "n_plots": access.visible_plots(u).count(),
    }
    if u.is_sz_admin:
        ctx.update(
            n_clients=access.visible_clients(u).count(),
            n_entities=access.visible_entities(u).count(),
            pending_invites=SupplierInvitation.objects.filter(open_invitation_q()).select_related("client")[:10],
            recent=AuditLog.objects.select_related("client", "supplier")[:12],
            clients=access.visible_clients(u).annotate(
                n_entities=Count("entities", distinct=True), n_suppliers=Count("supplier_links", distinct=True))[:10],
        )
        template = "core/dashboard_sz.html"
    elif u.is_client_user:
        links = access.visible_links(u).prefetch_related("entities")
        suppliers = []
        for link in links:
            s = link.supplier
            suppliers.append({
                "link": link,
                "products": access.visible_products(u).filter(supplier=s).count(),
                "plots": access.visible_plots(u).filter(supplier=s).count(),
                "plots_missing_products": access.visible_plots(u).filter(supplier=s, products__isnull=True).count(),
            })
        ctx.update(client=u.client_company, entities=access.visible_entities(u), suppliers=suppliers,
                   pending_invites=SupplierInvitation.objects.filter(open_invitation_q(), client=u.client_company)
                   if u.role == "client_admin" else [])
        template = "core/dashboard_client.html"
    else:
        products = access.visible_products(u)
        plots = access.visible_plots(u)
        todo = []
        if not access.visible_producers(u).exists():
            todo.append(("Register the producer of your raw material", "supply:producer_create"))
        if not products.exists():
            todo.append(("Register the products you supply", "supply:product_create"))
        if not plots.exists():
            todo.append(("Add the location where the raw material was grown or harvested", "supply:plot_create"))
        ctx.update(
            clients=access.visible_clients(u), todo=todo,
            products_without_source=products.annotate(n=Count("source_plots")).filter(n=0),
            products_not_shared=products.annotate(n=Count("clients")).filter(n=0),
            plots_without_product=plots.filter(products__isnull=True),
            products_missing_species=products.filter(commodity="wood").filter(Q(species_scientific="")),
        )
        template = "core/dashboard_supplier.html"
    return render(request, template, ctx)


def health(request):
    from django.db import connection
    with connection.cursor() as c:
        c.execute("SELECT PostGIS_Version()")
        c.fetchone()
    return HttpResponse("ok", content_type="text/plain")
