from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.audit.services import record, snapshot
from apps.core.emails import send_invitation_email
from apps.core.tokens import hash_token, invitation_expiry, new_token
from .decorators import role_required
from .forms import AccountFields, LoginForm, UserInviteForm
from .models import CLIENT_ROLES, Role, User, UserInvitation


class RateLimitedLoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def _key(self):
        ident = (self.request.POST.get("username") or "").lower()[:254]
        return f"login-attempts:{self.request.META.get('REMOTE_ADDR')}:{ident}"

    def post(self, request, *args, **kwargs):
        if cache.get(self._key(), 0) >= settings.LOGIN_RATE_LIMIT:
            form = self.get_form()
            form.errors.clear()
            form.add_error(None, "Too many sign-in attempts. Please wait 15 minutes and try again.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        key = self._key()
        cache.add(key, 0, settings.LOGIN_RATE_WINDOW)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, settings.LOGIN_RATE_WINDOW)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._key())
        response = super().form_valid(form)
        record(self.request, "auth.login", self.request.user)
        return response


@role_required(Role.SZ_ADMIN, Role.CLIENT_ADMIN, Role.SUPPLIER_ADMIN)
def team(request):
    u = request.user
    if u.is_sz_admin:
        members = User.objects.filter(role=Role.SZ_ADMIN)
        invites = UserInvitation.objects.none()
    elif u.role == Role.CLIENT_ADMIN:
        members = User.objects.filter(client_company_id=u.client_company_id)
        invites = UserInvitation.objects.filter(client_company_id=u.client_company_id)
    else:
        members = User.objects.filter(supplier_id=u.supplier_id)
        invites = UserInvitation.objects.filter(supplier_id=u.supplier_id)
    return render(request, "accounts/team.html", {"members": members.prefetch_related("permitted_entities"),
                                                  "invites": invites, "can_invite": not u.is_sz_admin})


def create_user_invitation(request, *, email, role, client=None, supplier=None, entities=()):
    raw, digest = new_token()
    inv = UserInvitation.objects.create(email=email, role=role, client_company=client, supplier=supplier,
                                        token_hash=digest, expires_at=invitation_expiry(), invited_by=request.user)
    if entities:
        inv.entities.set(entities)
    link = request.build_absolute_uri(reverse("accounts:accept_invite", args=[raw]))
    org = client or supplier
    send_invitation_email(email, f"You have been invited to {org} on SustainZone EUDR Gateway",
                          f"{request.user.full_name} has invited you to join {org} as {inv.get_role_display()}.", link)
    record(request, "user_invitation.created", inv, after=snapshot(inv), client=client, supplier=supplier)
    return inv, link


@role_required(Role.CLIENT_ADMIN, Role.SUPPLIER_ADMIN)
@require_http_methods(["GET", "POST"])
def invite_user(request):
    u = request.user
    if u.role == Role.CLIENT_ADMIN:
        roles, entity_qs = CLIENT_ROLES, u.client_company.entities.all()
    else:
        roles, entity_qs = (Role.SUPPLIER_ADMIN, Role.SUPPLIER_USER), None
    form = UserInviteForm(request.POST or None, roles=roles, entity_qs=entity_qs)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        entities = d.get("entities") if d["role"] == Role.CLIENT_ENTITY_USER else ()
        _, link = create_user_invitation(request, email=d["email"], role=d["role"],
                                         client=u.client_company if u.is_client_user else None,
                                         supplier=u.supplier if u.is_supplier_user else None, entities=entities)
        return render(request, "includes/invite_link.html", {"link": link, "email": d["email"],
                                                              "back": reverse("accounts:team")})
    return render(request, "generic/form.html", {"form": form, "title": "Invite a team member",
                                                 "submit": "Send invitation", "cancel": reverse("accounts:team")})


def _open_invitation(model, token):
    inv = model.objects.filter(token_hash=hash_token(token)).first()
    if not inv or inv.accepted_at or inv.revoked_at or inv.expires_at < timezone.now():
        return None
    return inv


@require_http_methods(["GET", "POST"])
def accept_invite(request, token):
    inv = _open_invitation(UserInvitation, token)
    if inv is None:
        return render(request, "accounts/invite_invalid.html", status=404)
    if request.user.is_authenticated:
        return render(request, "accounts/invite_logged_in.html")
    form = AccountFields(request.POST or None, initial={"email": inv.email})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            inv = UserInvitation.objects.select_for_update().get(pk=inv.pk)
            if inv.accepted_at:
                return render(request, "accounts/invite_invalid.html", status=404)
            user = User.objects.create_user(d["email"], d["password1"], full_name=d["full_name"], role=inv.role,
                                            client_company=inv.client_company, supplier=inv.supplier)
            if inv.role == Role.CLIENT_ENTITY_USER:
                user.permitted_entities.set(inv.entities.all())
            inv.accepted_at, inv.accepted_user = timezone.now(), user
            inv.save(update_fields=["accepted_at", "accepted_user"])
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            record(request, "user.registered", user, after=snapshot(user))
        messages.success(request, "Your account is ready.")
        return redirect("core:dashboard")
    org = inv.client_company or inv.supplier
    return render(request, "accounts/accept_invite.html", {"form": form, "inv": inv, "org": org})


@role_required(Role.CLIENT_ADMIN, Role.SUPPLIER_ADMIN)
@require_http_methods(["POST"])
def revoke_invite(request, pk):
    u = request.user
    qs = (UserInvitation.objects.filter(client_company_id=u.client_company_id) if u.is_client_user
          else UserInvitation.objects.filter(supplier_id=u.supplier_id))
    inv = get_object_or_404(qs, pk=pk, accepted_at__isnull=True, revoked_at__isnull=True)
    inv.revoked_at = timezone.now()
    inv.save(update_fields=["revoked_at"])
    record(request, "user_invitation.revoked", inv)
    messages.success(request, "Invitation revoked.")
    return redirect("accounts:team")
