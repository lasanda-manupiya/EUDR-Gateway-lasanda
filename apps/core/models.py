from django.db import models
from .countries import COUNTRY_CHOICES


class CountryField(models.CharField):
    """ISO 3166-1 alpha-2 country code."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 2)
        kwargs.setdefault("choices", COUNTRY_CHOICES)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs.pop("choices", None)
        return name, "apps.core.models.CountryField", args, kwargs


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
