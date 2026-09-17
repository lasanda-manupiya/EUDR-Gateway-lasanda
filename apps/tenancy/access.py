"""
Tenant isolation. EVERY read of tenant data in a view must start from one of
these querysets, and object lookups use get_object_or_404(<scoped qs>, pk=...),
so records outside the user's tenant resolve to 404 rather than 403
(no information about existence leaks).
"""
from django.db.models import Q

from apps.accounts.models import Role
from apps.supply.models import Evidence, Producer, Product, SourcePlot
from .models import ClientCompany, LegalEntity, LinkStatus, Supplier, SupplierClientLink


def _none(model):
    return model.objects.none()


def visible_clients(user):
    if user.is_sz_admin:
        return ClientCompany.objects.all()
    if user.is_client_user:
        return ClientCompany.objects.filter(pk=user.client_company_id)
    if user.is_supplier_user:
        return ClientCompany.objects.filter(supplier_links__supplier_id=user.supplier_id,
                                            supplier_links__status=LinkStatus.ACTIVE).distinct()
    return _none(ClientCompany)


def visible_entities(user):
    if user.is_sz_admin:
        return LegalEntity.objects.all()
    if user.role == Role.CLIENT_ADMIN:
        return LegalEntity.objects.filter(client_id=user.client_company_id)
    if user.role == Role.CLIENT_ENTITY_USER:
        return user.permitted_entities.filter(client_id=user.client_company_id)
    if user.is_supplier_user:
        return LegalEntity.objects.filter(supplier_links__supplier_id=user.supplier_id,
                                          supplier_links__status=LinkStatus.ACTIVE).distinct()
    return _none(LegalEntity)


def visible_links(user):
    qs = SupplierClientLink.objects.select_related("supplier", "client")
    if user.is_sz_admin:
        return qs
    if user.role == Role.CLIENT_ADMIN:
        return qs.filter(client_id=user.client_company_id)
    if user.role == Role.CLIENT_ENTITY_USER:
        return qs.filter(client_id=user.client_company_id, status=LinkStatus.ACTIVE,
                         entities__in=user.permitted_entities.all()).distinct()
    if user.is_supplier_user:
        return qs.filter(supplier_id=user.supplier_id)
    return qs.none()


def visible_suppliers(user):
    if user.is_sz_admin:
        return Supplier.objects.all()
    if user.is_supplier_user:
        return Supplier.objects.filter(pk=user.supplier_id)
    if user.is_client_user:
        ids = visible_links(user).filter(status=LinkStatus.ACTIVE).values("supplier_id")
        return Supplier.objects.filter(pk__in=ids)
    return _none(Supplier)


def visible_products(user):
    if user.is_sz_admin:
        return Product.objects.all()
    if user.is_supplier_user:
        return Product.objects.filter(supplier_id=user.supplier_id)
    if user.is_client_user:
        return Product.objects.filter(supplier__in=visible_suppliers(user),
                                      clients=user.client_company_id).distinct()
    return _none(Product)


def visible_plots(user):
    if user.is_sz_admin:
        return SourcePlot.objects.all()
    if user.is_supplier_user:
        return SourcePlot.objects.filter(supplier_id=user.supplier_id)
    if user.is_client_user:
        return SourcePlot.objects.filter(supplier__in=visible_suppliers(user),
                                         clients=user.client_company_id).distinct()
    return _none(SourcePlot)


def visible_producers(user):
    if user.is_sz_admin:
        return Producer.objects.all()
    if user.is_supplier_user:
        return Producer.objects.filter(suppliers=user.supplier_id).distinct()
    if user.is_client_user:
        return Producer.objects.filter(
            Q(pk__in=visible_products(user).values("producers")) |
            Q(pk__in=visible_plots(user).values("producer"))).distinct()
    return _none(Producer)


def visible_evidence(user):
    if user.is_sz_admin:
        return Evidence.objects.all()
    if user.is_supplier_user:
        return Evidence.objects.filter(supplier_id=user.supplier_id)
    if user.is_client_user:
        return Evidence.objects.filter(
            Q(product__in=visible_products(user)) | Q(source_plot__in=visible_plots(user)) |
            Q(producer__in=visible_producers(user))).distinct()
    return _none(Evidence)


def active_link_clients_for_supplier(supplier_id):
    return ClientCompany.objects.filter(supplier_links__supplier_id=supplier_id,
                                        supplier_links__status=LinkStatus.ACTIVE).distinct()


def can_manage_client(user, client):
    return user.is_sz_admin or (user.role == Role.CLIENT_ADMIN and user.client_company_id == client.pk)
