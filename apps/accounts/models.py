from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import Q


class Role(models.TextChoices):
    SZ_ADMIN = "sz_admin", "SustainZone Admin"
    CLIENT_ADMIN = "client_admin", "Client Company Admin"
    CLIENT_ENTITY_USER = "client_entity_user", "Client Entity User"
    SUPPLIER_ADMIN = "supplier_admin", "Supplier Admin"
    SUPPLIER_USER = "supplier_user", "Supplier User"


CLIENT_ROLES = (Role.CLIENT_ADMIN, Role.CLIENT_ENTITY_USER)
SUPPLIER_ROLES = (Role.SUPPLIER_ADMIN, Role.SUPPLIER_USER)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.update(role=Role.SZ_ADMIN, is_staff=True, is_superuser=True)
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    username = None
    first_name = None
    last_name = None
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=32, choices=Role.choices)
    client_company = models.ForeignKey("tenancy.ClientCompany", null=True, blank=True,
                                       on_delete=models.PROTECT, related_name="users")
    supplier = models.ForeignKey("tenancy.Supplier", null=True, blank=True,
                                 on_delete=models.PROTECT, related_name="users")
    permitted_entities = models.ManyToManyField("tenancy.LegalEntity", blank=True, related_name="permitted_users",
                                                help_text="Only used for Client Entity Users.")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        ordering = ["full_name", "email"]
        constraints = [
            models.CheckConstraint(
                name="user_role_matches_tenant",
                condition=(
                    Q(role=Role.SZ_ADMIN, client_company__isnull=True, supplier__isnull=True)
                    | Q(role__in=CLIENT_ROLES, client_company__isnull=False, supplier__isnull=True)
                    | Q(role__in=SUPPLIER_ROLES, supplier__isnull=False, client_company__isnull=True)
                ),
            )
        ]

    def __str__(self):
        return self.full_name or self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email

    @property
    def is_sz_admin(self):
        return self.role == Role.SZ_ADMIN

    @property
    def is_client_user(self):
        return self.role in CLIENT_ROLES

    @property
    def is_supplier_user(self):
        return self.role in SUPPLIER_ROLES

    @property
    def organisation_label(self):
        if self.is_sz_admin:
            return "SustainZone"
        if self.client_company_id:
            return self.client_company.name
        if self.supplier_id:
            return self.supplier.name
        return ""


class UserInvitation(models.Model):
    """Invitation for a person to join an existing client company or supplier."""
    email = models.EmailField()
    role = models.CharField(max_length=32, choices=Role.choices)
    client_company = models.ForeignKey("tenancy.ClientCompany", null=True, blank=True, on_delete=models.CASCADE)
    supplier = models.ForeignKey("tenancy.Supplier", null=True, blank=True, on_delete=models.CASCADE)
    entities = models.ManyToManyField("tenancy.LegalEntity", blank=True)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    revoked_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sent_user_invitations")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(
            name="user_invite_one_tenant",
            condition=(Q(role__in=CLIENT_ROLES, client_company__isnull=False, supplier__isnull=True)
                       | Q(role__in=SUPPLIER_ROLES, supplier__isnull=False, client_company__isnull=True)),
        )]


def _invitation_state(self):
    from django.utils import timezone
    if self.accepted_at:
        return "accepted"
    if self.revoked_at:
        return "revoked"
    return "expired" if self.expires_at < timezone.now() else "pending"


UserInvitation.state = property(_invitation_state)
