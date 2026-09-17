from django.core.paginator import Paginator
from django.shortcuts import render

from apps.accounts.decorators import role_required
from apps.accounts.models import Role
from .models import AuditLog


@role_required(Role.SZ_ADMIN, Role.CLIENT_ADMIN)
def audit_list(request):
    qs = AuditLog.objects.select_related("client", "supplier")
    if request.user.role == Role.CLIENT_ADMIN:
        qs = qs.filter(client_id=request.user.client_company_id)
    action = request.GET.get("action", "").strip()
    if action:
        qs = qs.filter(action__icontains=action)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "audit/list.html", {"page": page, "action": action})
