import datetime
import decimal

from django.forms.models import model_to_dict

from .models import AuditLog

SKIP_FIELDS = {"password", "token_hash", "geometry", "point", "file"}


def snapshot(obj, extra=None):
    if obj is None:
        return None
    data = {}
    for k, v in model_to_dict(obj).items():
        if k in SKIP_FIELDS:
            continue
        if isinstance(v, (datetime.date, datetime.datetime, decimal.Decimal)):
            v = str(v)
        elif isinstance(v, (list, tuple)):
            v = [getattr(i, "pk", i) for i in v]
        elif hasattr(v, "pk"):
            v = v.pk
        data[k] = v
    if extra:
        data.update(extra)
    return data


def _ip(request):
    return request.META.get("REMOTE_ADDR") if request else None


def _derive(obj, attr, model_name):
    if obj._meta.model_name == model_name:
        return obj
    return getattr(obj, attr, None) if hasattr(obj, f"{attr}_id") else None


def record(request, action, obj, before=None, after=None, client=None, supplier=None):
    user = getattr(request, "user", None)
    user = user if user is not None and user.is_authenticated else None
    client = client or _derive(obj, "client", "clientcompany") or (user.client_company if user and user.client_company_id else None)
    supplier = supplier or _derive(obj, "supplier", "supplier") or (user.supplier if user and user.supplier_id else None)
    return AuditLog.objects.create(
        user=user, user_email=user.email if user else "", user_role=user.role if user else "",
        client=client, supplier=supplier, action=action, object_type=obj._meta.label,
        object_id=str(obj.pk), object_repr=str(obj)[:255], before=before, after=after, ip_address=_ip(request))
