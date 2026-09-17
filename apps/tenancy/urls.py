from django.urls import path
from . import views

app_name = "tenancy"
urlpatterns = [
    path("clients/", views.client_list, name="client_list"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/mine/", views.my_client, name="my_client"),
    path("clients/<int:pk>/", views.client_detail, name="client_detail"),
    path("clients/<int:pk>/edit/", views.client_edit, name="client_edit"),
    path("clients/<int:client_pk>/entities/new/", views.entity_create, name="entity_create"),
    path("clients/<int:client_pk>/suppliers/invite/", views.supplier_invite, name="supplier_invite"),
    path("entities/<int:pk>/", views.entity_detail, name="entity_detail"),
    path("entities/<int:pk>/edit/", views.entity_edit, name="entity_edit"),
    path("supplier-invitations/<int:pk>/revoke/", views.supplier_invite_revoke, name="supplier_invite_revoke"),
    path("register/supplier/<str:token>/", views.supplier_accept, name="supplier_accept"),
    path("suppliers/", views.supplier_list, name="supplier_list"),
    path("suppliers/<int:pk>/", views.supplier_detail, name="supplier_detail"),
    path("company/", views.my_supplier, name="my_supplier"),
    path("company/edit/", views.my_supplier_edit, name="my_supplier_edit"),
    path("company/factories/new/", views.factory_create, name="factory_create"),
]
