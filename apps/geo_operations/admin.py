from django.contrib import admin

from apps.geo_operations.models import GeoAsset, GeoAssetCategory, GeoAssetChangeLog


@admin.register(GeoAssetCategory)
class GeoAssetCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'geometry_type', 'color', 'is_active', 'sort_order')
    list_filter = ('geometry_type', 'is_active')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('sort_order', 'name')


@admin.register(GeoAsset)
class GeoAssetAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'geometry_type', 'operational_status', 'criticality', 'parcela', 'is_active', 'updated_at')
    list_filter = ('category', 'geometry_type', 'operational_status', 'criticality', 'is_active', 'is_deleted')
    search_fields = ('title', 'code', 'description', 'observations', 'parcela__codigo_parcela')
    readonly_fields = (
        'bbox',
        'center_lat',
        'center_lng',
        'length_m',
        'perimeter_m',
        'area_m2',
        'vertex_count',
        'created_by',
        'updated_by',
        'created_at',
        'updated_at',
    )
    autocomplete_fields = ('category', 'parcela', 'created_by', 'updated_by')
    ordering = ('category__sort_order', 'title')


@admin.register(GeoAssetChangeLog)
class GeoAssetChangeLogAdmin(admin.ModelAdmin):
    list_display = ('asset', 'action', 'user', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('asset__title', 'user__email')
    readonly_fields = ('asset', 'user', 'action', 'snapshot', 'created_at')
