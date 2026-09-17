from apps.accounts.models import Role


def navigation(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    items = [("core:dashboard", "Dashboard")]
    r = user.role
    if r == Role.SZ_ADMIN:
        items += [("tenancy:client_list", "Client companies"), ("tenancy:supplier_list", "Suppliers"),
                  ("supply:product_list", "Products"), ("supply:producer_list", "Producers"),
                  ("supply:plot_list", "Source locations"), ("audit:list", "Audit log")]
    elif r in (Role.CLIENT_ADMIN, Role.CLIENT_ENTITY_USER):
        items += [("tenancy:my_client", "Company & entities"), ("tenancy:supplier_list", "Suppliers"),
                  ("supply:product_list", "Products"), ("supply:plot_list", "Source locations")]
        if r == Role.CLIENT_ADMIN:
            items += [("accounts:team", "Team"), ("audit:list", "Audit log")]
    else:
        items += [("supply:product_list", "Products"), ("supply:producer_list", "Producers"),
                  ("supply:plot_list", "Source locations"), ("tenancy:my_supplier", "Company profile")]
        if r == Role.SUPPLIER_ADMIN:
            items += [("accounts:team", "Team")]
    return {"nav_items": items, "Role": Role}
