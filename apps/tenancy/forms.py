from django import forms

from apps.accounts.models import User
from .models import ClientCompany, LegalEntity, Supplier, SupplierFactory

TEXTAREA = forms.Textarea(attrs={"rows": 3})


class ClientCompanyForm(forms.ModelForm):
    class Meta:
        model = ClientCompany
        fields = ["name", "trading_name", "country", "address", "registration_number", "vat_number", "eori_number",
                  "company_size", "main_contact_name", "main_contact_email", "main_contact_phone",
                  "eudr_contact_name", "eudr_contact_email", "eudr_contact_phone", "status"]
        widgets = {"address": TEXTAREA}


class ClientCreateForm(ClientCompanyForm):
    admin_email = forms.EmailField(required=False, label="Client admin email",
                                   help_text="Optional. Sends a secure invitation to the first Client Company Admin.")

    def clean_admin_email(self):
        email = (self.cleaned_data.get("admin_email") or "").lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email


class LegalEntityForm(forms.ModelForm):
    class Meta:
        model = LegalEntity
        fields = ["name", "country", "address", "registration_number", "vat_number", "eori_number", "eudr_role",
                  "traces_operator_reference", "contact_name", "contact_email", "contact_phone", "is_active"]
        widgets = {"address": TEXTAREA}

    def __init__(self, *args, client, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client

    def clean_name(self):
        name = self.cleaned_data["name"]
        qs = LegalEntity.objects.filter(client=self.client, name__iexact=name).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This client already has an entity with that name.")
        return name


class SupplierInviteForm(forms.Form):
    supplier_name = forms.CharField(max_length=200)
    email = forms.EmailField(help_text="The person at the supplier who will register the company.")
    entities = forms.ModelMultipleChoiceField(queryset=None, required=False, widget=forms.CheckboxSelectMultiple,
                                              help_text="Legal entities that buy from this supplier.")
    message = forms.CharField(required=False, widget=TEXTAREA, help_text="Optional note included in the email.")

    def __init__(self, *args, client, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entities"].queryset = client.entities.filter(is_active=True)


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "country", "address", "company_number", "vat_number", "eori_number",
                  "contact_name", "contact_email", "contact_phone", "eudr_contact_name", "eudr_contact_email"]
        widgets = {"address": TEXTAREA}


class FactoryForm(forms.ModelForm):
    class Meta:
        model = SupplierFactory
        fields = ["name", "country", "address"]
        widgets = {"address": TEXTAREA}
