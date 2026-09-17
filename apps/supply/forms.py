import hashlib
import json
import os

from django import forms
from django.conf import settings

from apps.tenancy.access import active_link_clients_for_supplier
from .geo import GeometryError, parse_geojson
from .models import Evidence, EvidenceCategory, Producer, Product, SourcePlot

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
CHECKS = forms.CheckboxSelectMultiple


class SupplierScopedForm(forms.ModelForm):
    def __init__(self, *args, supplier, **kwargs):
        super().__init__(*args, **kwargs)
        self.supplier = supplier
        if "clients" in self.fields:
            qs = active_link_clients_for_supplier(supplier.pk)
            self.fields["clients"].queryset = qs
            if not self.instance.pk and qs.count() == 1:
                self.fields["clients"].initial = list(qs)
        if "producers" in self.fields:
            self.fields["producers"].queryset = Producer.objects.filter(suppliers=supplier)
        if "producer" in self.fields:
            self.fields["producer"].queryset = Producer.objects.filter(suppliers=supplier)
        if "products" in self.fields:
            self.fields["products"].queryset = Product.objects.filter(supplier=supplier)


class ProductForm(SupplierScopedForm):
    class Meta:
        model = Product
        fields = ["name", "product_code", "sku", "description", "commodity", "hs_code", "cn_code", "material",
                  "species_common", "species_scientific", "producers", "country_of_production", "unit", "clients"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "producers": CHECKS, "clients": CHECKS}
        labels = {"clients": "Customers who can see this product"}

    def clean_sku(self):
        sku = self.cleaned_data["sku"].strip()
        if sku and Product.objects.filter(supplier=self.supplier, sku__iexact=sku).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("You already have a product with this SKU.")
        return sku

    def clean(self):
        d = super().clean()
        for code in ("hs_code", "cn_code"):
            v = (d.get(code) or "").replace(" ", "").replace(".", "")
            if v and not v.isdigit():
                self.add_error(code, "Codes contain digits only (spaces and dots are ignored).")
            d[code] = v
        if d.get("hs_code") and len(d["hs_code"]) not in (4, 6):
            self.add_error("hs_code", "HS codes are 4 or 6 digits.")
        if d.get("cn_code") and len(d["cn_code"]) != 8:
            self.add_error("cn_code", "CN codes are 8 digits.")
        return d


class ProducerForm(forms.ModelForm):
    class Meta:
        model = Producer
        fields = ["name", "country", "address", "registration_number", "notes"]
        widgets = {"address": forms.Textarea(attrs={"rows": 3}), "notes": forms.Textarea(attrs={"rows": 3})}


class SourcePlotForm(SupplierScopedForm):
    geometry_geojson = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = SourcePlot
        fields = ["name", "plot_reference", "country", "producer", "products", "production_start", "production_end",
                  "harvest_start", "harvest_end", "description", "clients"]
        widgets = {"products": CHECKS, "clients": CHECKS, "description": forms.Textarea(attrs={"rows": 2}),
                   "production_start": DATE, "production_end": DATE, "harvest_start": DATE, "harvest_end": DATE}
        labels = {"clients": "Customers who can see this location"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.is_bound:
            from .geo import to_feature_collection
            fc = to_feature_collection(self.instance)
            self.initial["geometry_geojson"] = json.dumps(fc) if fc else ""

    def clean_geometry_geojson(self):
        try:
            self.parsed_geometry = parse_geojson(self.cleaned_data.get("geometry_geojson", ""))
        except GeometryError as exc:
            raise forms.ValidationError(str(exc))
        return self.cleaned_data["geometry_geojson"]

    def clean(self):
        d = super().clean()
        for a, b, label in (("production_start", "production_end", "Production"), ("harvest_start", "harvest_end", "Harvest")):
            if d.get(a) and d.get(b) and d[a] > d[b]:
                self.add_error(b, f"{label} end date is before the start date.")
        return d


ALLOWED_EXT = {".pdf": "application/pdf", ".csv": "text/csv", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
               ".xls": "application/vnd.ms-excel", ".png": "image/png",
               ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".geojson": "application/geo+json", ".json": "application/json"}
MAGIC = {".pdf": [b"%PDF"], ".png": [b"\x89PNG"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"],
         ".xlsx": [b"PK\x03\x04"], ".xls": [b"\xd0\xcf\x11\xe0"]}


class EvidenceForm(forms.ModelForm):
    class Meta:
        model = Evidence
        fields = ["file", "category", "description"]

    def clean_file(self):
        f = self.cleaned_data["file"]
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in ALLOWED_EXT:
            raise forms.ValidationError("Allowed file types: PDF, Excel, CSV, PNG, JPG, GeoJSON.")
        if f.size > settings.EVIDENCE_MAX_BYTES:
            raise forms.ValidationError(f"Files must be under {settings.EVIDENCE_MAX_BYTES // (1024 * 1024)} MB.")
        head = f.read(8)
        f.seek(0)
        if ext in MAGIC and not any(head.startswith(m) for m in MAGIC[ext]):
            raise forms.ValidationError("The file content does not match its extension.")
        if ext in (".geojson", ".json"):
            try:
                parse_geojson(f.read().decode("utf-8"))
            except (UnicodeDecodeError, GeometryError) as exc:
                raise forms.ValidationError(f"GeoJSON check failed: {exc}")
            f.seek(0)
        digest = hashlib.sha256()
        for chunk in f.chunks():
            digest.update(chunk)
        f.seek(0)
        self.meta = {"ext": ext, "sha256": digest.hexdigest(), "content_type": ALLOWED_EXT[ext]}
        return f
