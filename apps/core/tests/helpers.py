import json
import re

from django.core import mail

PASSWORD = "Correct-Horse-Battery-9"

POLYGON = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {
    "type": "Polygon", "coordinates": [[[6.95, 50.93], [6.96, 50.93], [6.96, 50.94], [6.95, 50.94], [6.95, 50.93]]]}}]}


def client_payload(name, **kw):
    data = {"name": name, "country": "DE", "address": "1 Hafenstrasse, Hamburg", "main_contact_name": "Main Contact",
            "main_contact_email": f"main@{name.lower().replace(' ', '')}.example", "status": "active",
            "company_size": "large"}
    data.update(kw)
    return data


def entity_payload(name, country="DE"):
    return {"name": name, "country": country, "address": "Address", "eudr_role": "operator", "is_active": "on"}


def supplier_payload(prefix="company", **kw):
    data = {"name": "Supplier A Timber", "country": "PL", "address": "Ul. Lesna 1, Poznan",
            "contact_name": "Anna Nowak", "contact_email": "anna@supplier-a.example"}
    data.update(kw)
    return {f"{prefix}-{k}": v for k, v in data.items()}


def account_payload(email, name="New Person", prefix="account"):
    data = {"full_name": name, "email": email, "password1": PASSWORD, "password2": PASSWORD}
    return {f"{prefix}-{k}" if prefix else k: v for k, v in data.items()}


def last_link():
    """Extract the invitation link from the most recent email (console/locmem backend)."""
    body = mail.outbox[-1].body
    return re.search(r"https?://\S+", body).group(0).replace("http://testserver", "")


def fc_json(obj=POLYGON):
    return json.dumps(obj)
