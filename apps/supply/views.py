import json
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import role_required
from apps.accounts.models import Role
from apps.audit.services import record, snapshot
from apps.tenancy import access
from .forms import EvidenceForm, ProducerForm, ProductForm, SourcePlotForm
from .geo import to_feature_collection
from .models import Evidence, GeometrySource


def _search(qs, q, *fields):
    if not q:
        return qs
    from django.db.models import Q
    cond = Q()
    for f in fields:
        cond |= Q(**{f"{f}__icontains": q})
    return qs.filter(cond)


# ---------------------------------------------------------------- products
@login_required
def product_list(request):
    q = request.GET.get("q", "").strip()
    qs = _search(access.visible_products(request.user).select_related("supplier"), q,
                 "name", "sku", "product_code", "cn_code", "hs_code", "species_scientific", "supplier__name")
    return render(request, "supply/product_list.html", {"products": qs, "q": q,
                                                        "can_create": request.user.role == Role.SUPPLIER_ADMIN})


@login_required
def product_detail(request, pk):
    product = get_object_or_404(access.visible_products(request.user).select_related("supplier"), pk=pk)
    return render(request, "supply/product_detail.html", {
        "product": product,
        "producers": access.visible_producers(request.user).filter(products=product),
        "plots": access.visible_plots(request.user).filter(products=product),
        "evidence": access.visible_evidence(request.user).filter(product=product),
        "can_edit": request.user.role == Role.SUPPLIER_ADMIN and product.supplier_id == request.user.supplier_id,
        "can_upload": request.user.is_supplier_user and product.supplier_id == request.user.supplier_id,
    })


@role_required(Role.SUPPLIER_ADMIN)
@require_http_methods(["GET", "POST"])
def product_edit(request, pk=None):
    supplier = request.user.supplier
    instance = get_object_or_404(access.visible_products(request.user), pk=pk) if pk else None
    before = snapshot(instance)
    form = ProductForm(request.POST or None, instance=instance, supplier=supplier)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            product = form.save(commit=False)
            product.supplier = supplier
            product.save()
            form.save_m2m()
            record(request, "product.updated" if pk else "product.created", product, before=before, after=snapshot(product))
        messages.success(request, "Product saved. You will not need to enter these details again for each order.")
        return redirect("supply:product_detail", pk=product.pk)
    return render(request, "generic/form.html", {
        "form": form, "title": "Edit product" if pk else "Register a product", "submit": "Save product",
        "intro": "Register each product once. Its details are reused for every purchase order.",
        "cancel": reverse("supply:product_detail", args=[pk]) if pk else reverse("supply:product_list")})


# ---------------------------------------------------------------- producers
@login_required
def producer_list(request):
    q = request.GET.get("q", "").strip()
    qs = _search(access.visible_producers(request.user), q, "name", "registration_number")
    return render(request, "supply/producer_list.html", {"producers": qs, "q": q,
                                                         "can_create": request.user.role == Role.SUPPLIER_ADMIN})


@login_required
def producer_detail(request, pk):
    producer = get_object_or_404(access.visible_producers(request.user), pk=pk)
    return render(request, "supply/producer_detail.html", {
        "producer": producer,
        "products": access.visible_products(request.user).filter(producers=producer),
        "plots": access.visible_plots(request.user).filter(producer=producer),
        "suppliers": access.visible_suppliers(request.user).filter(producers=producer),
        "evidence": access.visible_evidence(request.user).filter(producer=producer),
        "can_edit": request.user.role == Role.SUPPLIER_ADMIN and producer.created_by_supplier_id == request.user.supplier_id,
        "can_upload": request.user.is_supplier_user and producer.suppliers.filter(pk=request.user.supplier_id).exists(),
    })


@role_required(Role.SUPPLIER_ADMIN)
@require_http_methods(["GET", "POST"])
def producer_edit(request, pk=None):
    supplier = request.user.supplier
    instance = None
    if pk:
        instance = get_object_or_404(access.visible_producers(request.user), pk=pk, created_by_supplier=supplier)
    before = snapshot(instance)
    form = ProducerForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            producer = form.save(commit=False)
            if not pk:
                producer.created_by_supplier = supplier
            producer.save()
            producer.suppliers.add(supplier)
            record(request, "producer.updated" if pk else "producer.created", producer, before=before,
                   after=snapshot(producer), supplier=supplier)
        messages.success(request, "Producer saved.")
        return redirect("supply:producer_detail", pk=producer.pk)
    return render(request, "generic/form.html", {
        "form": form, "title": "Edit producer" if pk else "Register a producer", "submit": "Save producer",
        "intro": "A producer is whoever grew or harvested the raw material — a farm, forest owner or plantation. "
                 "If your company produced it itself, register your own company here.",
        "cancel": reverse("supply:producer_detail", args=[pk]) if pk else reverse("supply:producer_list")})


# ---------------------------------------------------------------- source plots
@login_required
def plot_list(request):
    q = request.GET.get("q", "").strip()
    qs = _search(access.visible_plots(request.user).select_related("supplier", "producer"), q,
                 "name", "plot_reference", "producer__name", "supplier__name")
    return render(request, "supply/plot_list.html", {"plots": qs, "q": q,
                                                     "can_create": request.user.role == Role.SUPPLIER_ADMIN})


@login_required
def plot_detail(request, pk):
    plot = get_object_or_404(access.visible_plots(request.user).select_related("supplier", "producer"), pk=pk)
    fc = to_feature_collection(plot)
    return render(request, "supply/plot_detail.html", {
        "plot": plot, "feature_collection": fc,
        "products": access.visible_products(request.user).filter(source_plots=plot),
        "evidence": access.visible_evidence(request.user).filter(source_plot=plot),
        "can_edit": request.user.role == Role.SUPPLIER_ADMIN and plot.supplier_id == request.user.supplier_id,
        "can_upload": request.user.is_supplier_user and plot.supplier_id == request.user.supplier_id,
    })


@login_required
def plot_geojson(request, pk):
    plot = get_object_or_404(access.visible_plots(request.user), pk=pk)
    response = JsonResponse(to_feature_collection(plot))
    if request.GET.get("download"):
        response["Content-Disposition"] = f'attachment; filename="source-plot-{plot.pk}.geojson"'
    return response


@role_required(Role.SUPPLIER_ADMIN)
@require_http_methods(["GET", "POST"])
def plot_edit(request, pk=None):
    supplier = request.user.supplier
    instance = get_object_or_404(access.visible_plots(request.user), pk=pk) if pk else None
    before = snapshot(instance, {"area_ha": str(instance.area_ha)} if instance else None)
    old_wkt = (instance.geometry or instance.point).wkt if instance else None
    form = SourcePlotForm(request.POST or None, instance=instance, supplier=supplier)
    if request.method == "POST" and form.is_valid():
        g = form.parsed_geometry
        with transaction.atomic():
            plot = form.save(commit=False)
            plot.supplier = supplier
            plot.geometry, plot.point = g["geometry"], g["point"]
            plot.area_ha = round(g["area_ha"], 4) if g["area_ha"] is not None else None
            new_wkt = (plot.geometry or plot.point).wkt
            if new_wkt != old_wkt:
                plot.geometry_updated_at = timezone.now()
                source = request.POST.get("geometry_origin", "")
                plot.geometry_source = source if source in GeometrySource.values else GeometrySource.DRAWN
            plot.save()
            form.save_m2m()
            after = snapshot(plot, {"geometry_changed": new_wkt != old_wkt, "location_type": plot.location_type,
                                    "bbox": list((plot.geometry or plot.point).extent)})
            record(request, "source_plot.updated" if pk else "source_plot.created", plot, before=before, after=after)
        messages.success(request, "Source location saved.")
        return redirect("supply:plot_detail", pk=plot.pk)
    return render(request, "supply/plot_form.html", {"form": form, "plot": instance})


# ---------------------------------------------------------------- evidence
ATTACH_TARGETS = {"product": access.visible_products, "producer": access.visible_producers, "source_plot": access.visible_plots}


@role_required(Role.SUPPLIER_ADMIN, Role.SUPPLIER_USER)
@require_http_methods(["GET", "POST"])
def evidence_upload(request, target, pk):
    if target not in ATTACH_TARGETS:
        raise Http404
    obj = get_object_or_404(ATTACH_TARGETS[target](request.user), pk=pk)
    detail_url = reverse({"product": "supply:product_detail", "producer": "supply:producer_detail",
                          "source_plot": "supply:plot_detail"}[target], args=[pk])
    form = EvidenceForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        ev = form.save(commit=False)
        ev.supplier = request.user.supplier
        ev.original_name = os.path.basename(form.cleaned_data["file"].name)[:255]
        ev.size_bytes = form.cleaned_data["file"].size
        ev.sha256, ev.content_type = form.meta["sha256"], form.meta["content_type"]
        ev.uploaded_by = request.user
        setattr(ev, target, obj)
        ev.save()
        record(request, "evidence.uploaded", ev, after={"name": ev.original_name, "sha256": ev.sha256,
                                                        "attached_to": f"{target}:{pk}", "category": ev.category})
        messages.success(request, "File uploaded.")
        return redirect(detail_url)
    return render(request, "generic/form.html", {"form": form, "title": f"Upload evidence for {obj}", "multipart": True,
                                                 "submit": "Upload", "cancel": detail_url,
                                                 "intro": "Files are stored privately. Only you, SustainZone and the "
                                                          "customers you share this record with can download them."})


@login_required
def evidence_download(request, pk):
    ev = get_object_or_404(access.visible_evidence(request.user), pk=pk)
    record(request, "evidence.downloaded", ev, supplier=ev.supplier)
    return FileResponse(ev.file.open("rb"), as_attachment=True, filename=ev.original_name,
                        content_type=ev.content_type)
