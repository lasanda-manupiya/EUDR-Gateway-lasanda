from django.urls import path
from . import views

app_name = "supply"
urlpatterns = [
    path("products/", views.product_list, name="product_list"),
    path("products/new/", views.product_edit, name="product_create"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("producers/", views.producer_list, name="producer_list"),
    path("producers/new/", views.producer_edit, name="producer_create"),
    path("producers/<int:pk>/", views.producer_detail, name="producer_detail"),
    path("producers/<int:pk>/edit/", views.producer_edit, name="producer_edit"),
    path("sources/", views.plot_list, name="plot_list"),
    path("sources/new/", views.plot_edit, name="plot_create"),
    path("sources/<int:pk>/", views.plot_detail, name="plot_detail"),
    path("sources/<int:pk>/edit/", views.plot_edit, name="plot_edit"),
    path("sources/<int:pk>/geojson/", views.plot_geojson, name="plot_geojson"),
    path("evidence/upload/<str:target>/<int:pk>/", views.evidence_upload, name="evidence_upload"),
    path("evidence/<int:pk>/download/", views.evidence_download, name="evidence_download"),
]
