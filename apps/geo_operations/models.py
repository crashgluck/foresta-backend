from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from apps.core.models import BaseDomainModel
from apps.geo_operations.services.geometry import validate_geojson_geometry


def geo_asset_photo_upload_to(instance, filename):
    return f'geo/assets/photos/{filename}'


class GeoGeometryType(models.TextChoices):
    POINT = 'POINT', 'Punto'
    LINE = 'LINE', 'Linea'
    POLYGON = 'POLYGON', 'Poligono'
    ANY = 'ANY', 'Cualquiera'


class GeoServiceType(models.TextChoices):
    ELECTRIC = 'ELECTRIC', 'Servicio electrico'
    WATER = 'WATER', 'Servicio de aguas'
    SECURITY = 'SECURITY', 'Seguridad'
    ROADS = 'ROADS', 'Vialidad'
    GREEN_AREAS = 'GREEN_AREAS', 'Areas verdes'
    RISK = 'RISK', 'Riesgos'
    INSPECTION = 'INSPECTION', 'Inspeccion en terreno'
    GENERAL = 'GENERAL', 'General'


class GeoAssetStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Operativo'
    MAINTENANCE = 'MAINTENANCE', 'En mantencion'
    REVIEW = 'REVIEW', 'Requiere revision'
    OUT_OF_SERVICE = 'OUT_OF_SERVICE', 'Fuera de servicio'
    UNKNOWN = 'UNKNOWN', 'Sin estado'


class GeoAssetCriticality(models.TextChoices):
    LOW = 'LOW', 'Baja'
    MEDIUM = 'MEDIUM', 'Media'
    HIGH = 'HIGH', 'Alta'
    CRITICAL = 'CRITICAL', 'Critica'


class GeoAssetCategory(BaseDomainModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    service_type = models.CharField(max_length=30, choices=GeoServiceType.choices, default=GeoServiceType.GENERAL, db_index=True)
    geometry_type = models.CharField(max_length=20, choices=GeoGeometryType.choices, default=GeoGeometryType.ANY, db_index=True)
    color = models.CharField(max_length=9, default='#2563eb')
    icon = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=100, db_index=True)
    extra_schema = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Categoria georreferenciada'
        verbose_name_plural = 'Categorias georreferenciadas'

    def __str__(self):
        return self.name

    def clean(self):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        if not self.color.startswith('#') or len(self.color) not in {4, 7, 9}:
            raise ValidationError({'color': 'Usa color hexadecimal. Ej: #2563eb'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class GeoAsset(BaseDomainModel):
    title = models.CharField(max_length=180)
    code = models.CharField(max_length=80, blank=True, db_index=True)
    category = models.ForeignKey(GeoAssetCategory, on_delete=models.PROTECT, related_name='assets')
    description = models.TextField(blank=True)
    geometry_type = models.CharField(max_length=20, choices=GeoGeometryType.choices, db_index=True)
    geometry = models.JSONField()
    properties = models.JSONField(default=dict, blank=True)
    operational_status = models.CharField(max_length=20, choices=GeoAssetStatus.choices, default=GeoAssetStatus.ACTIVE, db_index=True)
    criticality = models.CharField(
        max_length=20,
        choices=GeoAssetCriticality.choices,
        default=GeoAssetCriticality.MEDIUM,
        db_index=True,
    )
    installation_date = models.DateField(null=True, blank=True)
    last_inspection_date = models.DateField(null=True, blank=True)
    observations = models.TextField(blank=True)
    parcela = models.ForeignKey('parcels.Parcel', on_delete=models.SET_NULL, null=True, blank=True, related_name='geo_assets')
    photo = models.FileField(upload_to=geo_asset_photo_upload_to, blank=True)
    photo_original_name = models.CharField(max_length=255, blank=True)
    photo_content_type = models.CharField(max_length=80, blank=True)
    photo_size = models.PositiveIntegerField(default=0)
    photo_width = models.PositiveIntegerField(default=0)
    photo_height = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    bbox = models.JSONField(default=list, blank=True)
    min_lng = models.FloatField(null=True, blank=True, db_index=True)
    min_lat = models.FloatField(null=True, blank=True, db_index=True)
    max_lng = models.FloatField(null=True, blank=True, db_index=True)
    max_lat = models.FloatField(null=True, blank=True, db_index=True)
    center_lng = models.FloatField(null=True, blank=True)
    center_lat = models.FloatField(null=True, blank=True)
    length_m = models.FloatField(default=0)
    perimeter_m = models.FloatField(default=0)
    area_m2 = models.FloatField(default=0)
    vertex_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['category__sort_order', 'title']
        indexes = [
            models.Index(fields=['is_deleted', 'is_active', 'category']),
            models.Index(fields=['geometry_type', 'operational_status', 'criticality']),
            models.Index(fields=['min_lng', 'min_lat', 'max_lng', 'max_lat']),
        ]
        verbose_name = 'Elemento georreferenciado'
        verbose_name_plural = 'Elementos georreferenciados'

    def __str__(self):
        return self.title

    def clean(self):
        category_geometry_type = self.category.geometry_type if self.category_id else GeoGeometryType.ANY
        summary = validate_geojson_geometry(self.geometry, allowed_geometry_type=category_geometry_type)
        self.geometry_type = summary.geometry_type
        self.bbox = list(summary.bbox)
        self.min_lng, self.min_lat, self.max_lng, self.max_lat = summary.bbox
        self.center_lng, self.center_lat = summary.center
        self.vertex_count = summary.vertex_count
        self.length_m = summary.length_m
        self.perimeter_m = summary.perimeter_m
        self.area_m2 = summary.area_m2

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class GeoAssetChangeLog(models.Model):
    asset = models.ForeignKey(GeoAsset, on_delete=models.CASCADE, related_name='change_logs')
    user = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='geo_asset_change_logs')
    action = models.CharField(max_length=40)
    snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Cambio de elemento georreferenciado'
        verbose_name_plural = 'Cambios de elementos georreferenciados'

    def __str__(self):
        return f'{self.asset_id} {self.action}'
