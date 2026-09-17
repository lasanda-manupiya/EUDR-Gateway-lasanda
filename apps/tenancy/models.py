from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import CountryField, TimeStamped


class CompanySize(models.TextChoices):
    MICRO = "micro", "Micro"
    SMALL = "small", "Small"
    MEDIUM = "medium", "Medium"
    LARGE = "large", "Large"


class ClientStatus(models.TextChoices):
    ONBOARDING = "onboarding", "Onboarding"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"


class ClientCompany(TimeStamped):
    name = models.CharField("Company name", max_length=200, unique=True)
    trading_name = models.CharField(max_length=200, blank=True)
    country = CountryField()
    address = models.TextField()
    registration_number = models.CharField(max_length=64, blank=True)
    vat_number = models.CharField("VAT number", max_length=32, blank=True)
    eori_number = models.CharField("EORI number", max_length=32, blank=True,
                                   help_text="Where applicable (EU customs identifier).")
    company_size = models.CharField(max_length=16, choices=CompanySize.choices, blank=True)
    main_contact_name = models.CharField(max_length=150)
    main_contact_email = models.EmailField()
    main_contact_phone = models.CharField(max_length=40, blank=True)
    eudr_contact_name = models.CharField("EUDR contact name", max_length=150, blank=True)
    eudr_contact_email = models.EmailField("EUDR contact email", blank=True)
    eudr_contact_phone = models.CharField("EUDR contact phone", max_length=40, blank=True)
    status = models.CharField(max_length=16, choices=ClientStatus.choices, default=ClientStatus.ONBOARDING)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "client companies"

    def __str__(self):
        return self.name


class EudrRole(models.TextChoices):
    OPERATOR = "operator", "Operator"
    TRADER_SME = "trader_sme", "Trader (SME)"
    TRADER_NON_SME = "trader_non_sme", "Trader (non-SME)"
    DOWNSTREAM_OPERATOR = "downstream_operator", "Downstream operator"
    NOT_DETERMINED = "not_determined", "Not yet determined"


class LegalEntity(TimeStamped):
    client = models.ForeignKey(ClientCompany, on_delete=models.CASCADE, related_name="entities")
    name = models.CharField("Entity name", max_length=200)
    country = CountryField()
    address = models.TextField()
    registration_number = models.CharField("Company registration number", max_length=64, blank=True)
    vat_number = models.CharField("VAT number", max_length=32, blank=True)
    eori_number = models.CharField("EORI number", max_length=32, blank=True)
    eudr_role = models.CharField("EUDR role", max_length=32, choices=EudrRole.choices,
                                 default=EudrRole.NOT_DETERMINED)
    traces_operator_reference = models.CharField(
        "TRACES registration reference", max_length=64, blank=True,
        help_text="Recorded manually. No TRACES integration is connected.")
    contact_name = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["client__name", "name"]
        verbose_name_plural = "legal entities"
        constraints = [models.UniqueConstraint(fields=["client", "name"], name="entity_unique_name_per_client")]

    def __str__(self):
        return self.name


class SupplierStatus(models.TextChoices):
    REGISTERED = "registered", "Registered"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"


class Supplier(TimeStamped):
    """A supplier organisation. Registered once; may be linked to many clients."""
    name = models.CharField("Supplier company name", max_length=200)
    country = CountryField()
    address = models.TextField()
    company_number = models.CharField(max_length=64, blank=True)
    vat_number = models.CharField("VAT number", max_length=32, blank=True)
    eori_number = models.CharField("EORI number", max_length=32, blank=True, help_text="Where applicable.")
    contact_name = models.CharField(max_length=150)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=40, blank=True)
    eudr_contact_name = models.CharField("EUDR contact name", max_length=150, blank=True,
                                         help_text="The person who can answer questions about product origin.")
    eudr_contact_email = models.EmailField("EUDR contact email", blank=True)
    status = models.CharField(max_length=16, choices=SupplierStatus.choices, default=SupplierStatus.REGISTERED)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SupplierFactory(TimeStamped):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="factories")
    name = models.CharField(max_length=200)
    country = CountryField()
    address = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "supplier factories"

    def __str__(self):
        return self.name


class LinkStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"


class SupplierClientLink(TimeStamped):
    """The relationship that grants a client visibility of a supplier."""
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="client_links")
    client = models.ForeignKey(ClientCompany, on_delete=models.CASCADE, related_name="supplier_links")
    entities = models.ManyToManyField(LegalEntity, blank=True, related_name="supplier_links",
                                      help_text="Legal entities that buy from this supplier.")
    status = models.CharField(max_length=16, choices=LinkStatus.choices, default=LinkStatus.ACTIVE)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["client__name", "supplier__name"]
        constraints = [models.UniqueConstraint(fields=["supplier", "client"], name="supplier_client_unique")]

    def __str__(self):
        return f"{self.supplier} → {self.client}"


class SupplierInvitation(models.Model):
    client = models.ForeignKey(ClientCompany, on_delete=models.CASCADE, related_name="supplier_invitations")
    entities = models.ManyToManyField(LegalEntity, blank=True)
    supplier_name = models.CharField(max_length=200)
    email = models.EmailField()
    message = models.TextField(blank=True)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    revoked_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def state(self):
        if self.accepted_at:
            return "accepted"
        if self.revoked_at:
            return "revoked"
        if self.expires_at < timezone.now():
            return "expired"
        return "pending"


def open_invitation_q():
    return Q(accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now())
