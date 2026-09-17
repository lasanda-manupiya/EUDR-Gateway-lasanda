from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Append-only record of significant actions."""
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    user_email = models.EmailField(blank=True)
    user_role = models.CharField(max_length=32, blank=True)
    client = models.ForeignKey("tenancy.ClientCompany", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    supplier = models.ForeignKey("tenancy.Supplier", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=64, db_index=True)
    object_type = models.CharField(max_length=64)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["object_type", "object_id"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("Audit log entries are immutable")
        super().save(*args, **kwargs)
