from django.conf import settings
from django.contrib.gis.db import models as gis
from django.db import models

from apps.core.models import CountryField, TimeStamped


class Commodity(models.TextChoices):
    CATTLE = "cattle", "Cattle"
    COCOA = "cocoa", "Cocoa"
    COFFEE = "coffee", "Coffee"
    OIL_PALM = "oil_palm", "Oil palm"
    RUBBER = "rubber", "Rubber"
    SOYA = "soya", "Soya"
    WOOD = "wood", "Wood"


class Unit(models.TextChoices):
    KG = "kg", "Kilograms (kg)"
    TONNE = "t", "Tonnes (t)"
    M3 = "m3", "Cubic metres (m³)"
    PIECE = "pcs", "Pieces"
    HEAD = "head", "Head (cattle)"


class Producer(TimeStamped):
    """The company or person that grew, harvested or produced the commodity."""
    name = models.CharField("Producer name", max_length=200,
                            help_text="The farm, forest owner, plantation or company that produced the raw material. "
                                      "This may be different from your own company.")
    country = CountryField(help_text="Country where this producer operates.")
    address = models.TextField(blank=True)
    registration_number = models.CharField(max_length=64, blank=True,
                                           help_text="Business or forestry licence registration, if known.")
    notes = models.TextField(blank=True)
    suppliers = models.ManyToManyField("tenancy.Supplier", related_name="producers",
                                       help_text="Suppliers that source from this producer.")
    created_by_supplier = models.ForeignKey("tenancy.Supplier", on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(TimeStamped):
    supplier = models.ForeignKey("tenancy.Supplier", on_delete=models.PROTECT, related_name="products")
    clients = models.ManyToManyField(
        "tenancy.ClientCompany", related_name="shared_products",
        help_text="Which of your customers can see this product. Other customers will not see it.")
    name = models.CharField("Product name", max_length=200)
    product_code = models.CharField(max_length=64, blank=True)
    sku = models.CharField("SKU", max_length=64, blank=True, help_text="Your stock keeping unit code, if you use one.")
    description = models.TextField(blank=True)
    commodity = models.CharField(max_length=16, choices=Commodity.choices,
                                 help_text="The EUDR raw material this product contains or is made from.")
    hs_code = models.CharField("HS code", max_length=12, blank=True,
                               help_text="Harmonised System code (6 digits), usually on your customs or export paperwork. "
                                         "Example: 4407 91 for sawn oak.")
    cn_code = models.CharField("CN code", max_length=12, blank=True,
                               help_text="EU Combined Nomenclature code (8 digits). Example: 4407 91 15.")
    material = models.CharField(max_length=120, blank=True, help_text="Example: solid oak, plywood, cocoa butter.")
    species_common = models.CharField("Species (common name)", max_length=120, blank=True,
                                      help_text="Required for wood. Example: European oak.")
    species_scientific = models.CharField("Scientific species name", max_length=120, blank=True,
                                          help_text="Latin name. Example: Quercus robur. Ask the sawmill or producer if unsure.")
    producers = models.ManyToManyField(Producer, blank=True, related_name="products")
    country_of_production = CountryField(blank=True, help_text="Where the raw material was grown or harvested — "
                                                               "not where the product was manufactured.")
    unit = models.CharField(max_length=8, choices=Unit.choices, default=Unit.KG)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["supplier", "sku"], name="product_unique_sku_per_supplier",
                                               condition=~models.Q(sku=""))]

    def __str__(self):
        return f"{self.name}{' (' + self.sku + ')' if self.sku else ''}"


class GeometrySource(models.TextChoices):
    DRAWN = "drawn", "Drawn on map"
    UPLOADED = "uploaded", "Uploaded / pasted GeoJSON"
    COORDINATES = "coordinates", "Entered coordinates"


class SourcePlot(TimeStamped):
    """Production or harvesting location. Geometry is stored in PostGIS (WGS84)."""
    supplier = models.ForeignKey("tenancy.Supplier", on_delete=models.PROTECT, related_name="source_plots")
    clients = models.ManyToManyField("tenancy.ClientCompany", related_name="shared_source_plots",
                                     help_text="Which of your customers can see this location.")
    name = models.CharField("Source name", max_length=200,
                            help_text="A name you will recognise. Example: North block, Hofmann forest.")
    plot_reference = models.CharField(max_length=100, blank=True,
                                      help_text="Land registry, concession or forest compartment reference, if any.")
    country = CountryField(help_text="Country where the land is located.")
    producer = models.ForeignKey(Producer, null=True, blank=True, on_delete=models.PROTECT, related_name="source_plots")
    products = models.ManyToManyField(Product, blank=True, related_name="source_plots")
    production_start = models.DateField(null=True, blank=True)
    production_end = models.DateField(null=True, blank=True)
    harvest_start = models.DateField(null=True, blank=True)
    harvest_end = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    geometry = gis.MultiPolygonField(srid=4326, null=True, blank=True)
    point = gis.PointField(srid=4326, null=True, blank=True)
    area_ha = models.DecimalField("Area (ha)", max_digits=14, decimal_places=4, null=True, blank=True)
    geometry_source = models.CharField(max_length=16, choices=GeometrySource.choices, blank=True)
    geometry_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.CheckConstraint(name="plot_has_location",
                                              condition=models.Q(geometry__isnull=False) | models.Q(point__isnull=False))]
        indexes = [gis.Index(fields=["plot_reference"])]

    def __str__(self):
        return self.name

    @property
    def location_type(self):
        if self.geometry:
            n = len(self.geometry)
            return "Polygon" if n == 1 else f"{n} polygons"
        return "Point" if self.point else "None"


def evidence_path(instance, filename):
    import uuid
    return f"evidence/supplier_{instance.supplier_id}/{uuid.uuid4().hex}"


class EvidenceCategory(models.TextChoices):
    ORIGIN = "origin", "Origin / harvesting evidence"
    LEGALITY = "legality", "Legality (permits, licences, concessions)"
    PRODUCT = "product", "Product specification"
    PRODUCER = "producer", "Producer registration"
    GEOSPATIAL = "geospatial", "Geospatial file"
    OTHER = "other", "Other supporting document"


class Evidence(models.Model):
    supplier = models.ForeignKey("tenancy.Supplier", on_delete=models.PROTECT, related_name="evidence")
    file = models.FileField(upload_to=evidence_path)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    category = models.CharField(max_length=16, choices=EvidenceCategory.choices)
    description = models.CharField(max_length=255, blank=True)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.CASCADE, related_name="evidence")
    producer = models.ForeignKey(Producer, null=True, blank=True, on_delete=models.CASCADE, related_name="evidence")
    source_plot = models.ForeignKey(SourcePlot, null=True, blank=True, on_delete=models.CASCADE, related_name="evidence")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name_plural = "evidence"
        constraints = [models.CheckConstraint(
            name="evidence_attached_to_record",
            condition=models.Q(product__isnull=False) | models.Q(producer__isnull=False) | models.Q(source_plot__isnull=False))]

    def __str__(self):
        return self.original_name
