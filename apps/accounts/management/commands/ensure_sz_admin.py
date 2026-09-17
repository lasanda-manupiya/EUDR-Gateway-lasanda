"""Create the first SustainZone Admin from environment variables if none exists.
Used on hosts without shell access. Does nothing once an admin exists."""
import os
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from apps.accounts.models import Role, User


class Command(BaseCommand):
    help = "Create a SustainZone Admin from SZ_ADMIN_EMAIL / SZ_ADMIN_PASSWORD / SZ_ADMIN_NAME if none exists."

    def handle(self, *args, **kw):
        if User.objects.filter(role=Role.SZ_ADMIN).exists():
            self.stdout.write("SustainZone Admin already exists; nothing to do.")
            return
        email, password = os.environ.get("SZ_ADMIN_EMAIL"), os.environ.get("SZ_ADMIN_PASSWORD")
        if not email or not password:
            self.stdout.write(self.style.WARNING("No SustainZone Admin exists and SZ_ADMIN_EMAIL / SZ_ADMIN_PASSWORD are not set."))
            return
        user = User(email=email.lower().strip(), full_name=os.environ.get("SZ_ADMIN_NAME", "SustainZone Admin"), role=Role.SZ_ADMIN)
        try:
            password_validation.validate_password(password, user)
        except ValidationError as exc:
            self.stdout.write(self.style.ERROR("SZ_ADMIN_PASSWORD rejected: " + " ".join(exc.messages)))
            return
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"SustainZone Admin {user.email} created."))
