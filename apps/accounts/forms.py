from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import Role, User


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}))


class AccountFields(forms.Form):
    """Personal account fields used when accepting any invitation."""
    full_name = forms.CharField(max_length=150, label="Your full name")
    email = forms.EmailField(label="Your email")
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="At least 12 characters. Avoid common or purely numeric passwords.")
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Log in instead.")
        return email

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1:
            try:
                password_validation.validate_password(p1, User(email=data.get("email", ""), full_name=data.get("full_name", "")))
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return data


class UserInviteForm(forms.Form):
    email = forms.EmailField()
    role = forms.ChoiceField()
    entities = forms.ModelMultipleChoiceField(queryset=None, required=False, widget=forms.CheckboxSelectMultiple,
                                              help_text="Client Entity Users only see records for these entities.")

    def __init__(self, *args, roles, entity_qs=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [(r.value, r.label) for r in roles]
        if entity_qs is None:
            del self.fields["entities"]
        else:
            self.fields["entities"].queryset = entity_qs

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        data = super().clean()
        if data.get("role") == Role.CLIENT_ENTITY_USER and not data.get("entities"):
            self.add_error("entities", "Select at least one legal entity for an entity user.")
        return data
