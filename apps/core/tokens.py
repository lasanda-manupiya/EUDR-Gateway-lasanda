import hashlib
import secrets
from datetime import timedelta
from django.conf import settings
from django.utils import timezone


def new_token():
    """Return (raw_token, sha256_hash). Only the hash is stored."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def invitation_expiry():
    return timezone.now() + timedelta(days=settings.INVITATION_TTL_DAYS)
