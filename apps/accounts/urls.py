from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.RateLimitedLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("team/", views.team, name="team"),
    path("team/invite/", views.invite_user, name="invite_user"),
    path("team/invites/<int:pk>/revoke/", views.revoke_invite, name="revoke_invite"),
    path("invite/<str:token>/", views.accept_invite, name="accept_invite"),
]
