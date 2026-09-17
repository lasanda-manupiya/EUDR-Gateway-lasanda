import pycountry

COUNTRY_CHOICES = sorted(((c.alpha_2, c.name) for c in pycountry.countries), key=lambda x: x[1])
COUNTRY_NAMES = dict(COUNTRY_CHOICES)
