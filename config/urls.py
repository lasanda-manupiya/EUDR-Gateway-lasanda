from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.tenancy.urls")),
    path("", include("apps.supply.urls")),
    path("audit/", include("apps.audit.urls")),
]
