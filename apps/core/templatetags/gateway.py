from django import template
from apps.core.countries import COUNTRY_NAMES

register = template.Library()


@register.filter
def country_name(code):
    return COUNTRY_NAMES.get(code, code or "—")


@register.filter
def dash(value):
    return value if value not in (None, "") else "—"


@register.inclusion_tag("includes/field.html")
def field(bound_field):
    return {"f": bound_field}
