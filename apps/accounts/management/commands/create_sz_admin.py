import getpass
from django.contrib.auth import password_validation
from django.core.management.base import BaseCommand, CommandError
from apps.accounts.models import Role, User


class Command(BaseCommand):
    help = "Create a SustainZone Admin account."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--password", help="Omit to be prompted (recommended).")

    def handle(self, *args, email, name, password=None, **kw):
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("A user with that email already exists.")
        password = password or getpass.getpass("Password: ")
        user = User(email=email.lower(), full_name=name, role=Role.SZ_ADMIN)
        password_validation.validate_password(password, user)
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"SustainZone Admin {email} created."))
