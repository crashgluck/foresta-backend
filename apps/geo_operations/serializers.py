from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.geo_operations.models import (
    GeoAsset,
    GeoAssetCategory,
    GeoAssetCriticality,
    GeoAssetStatus,
)
from apps.geo_operations.services.geometry import validate_geojson_geometry
from apps.parcels.models import Parcel


class GeoAssetCategorySerializer(serializers.ModelSerializer):
    assets_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = GeoAssetCategory
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'geometry_type',
            'color',
            'icon',
            'is_active',
            'sort_order',
            'extra_schema',
            'assets_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class GeoAssetSerializer(serializers.ModelSerializer):
    category_detail = GeoAssetCategorySerializer(source='category', read_only=True)
    parcela_code = serializers.CharField(source='parcela.codigo_parcela', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    updated_by_name = serializers.CharField(source='updated_by.full_name', read_only=True)
    parcela = serializers.PrimaryKeyRelatedField(queryset=Parcel.objects.all(), required=False, allow_null=True)

    class Meta:
        model = GeoAsset
        fields = [
            'id',
            'title',
            'code',
            'category',
            'category_detail',
            'description',
            'geometry_type',
            'geometry',
            'properties',
            'operational_status',
            'criticality',
            'installation_date',
            'last_inspection_date',
            'observations',
            'parcela',
            'parcela_code',
            'is_active',
            'bbox',
            'center_lat',
            'center_lng',
            'length_m',
            'perimeter_m',
            'area_m2',
            'vertex_count',
            'created_by',
            'created_by_name',
            'updated_by',
            'updated_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'geometry_type',
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
        ]

    def validate(self, attrs):
        instance = self.instance
        geometry = attrs.get('geometry', instance.geometry if instance else None)
        category = attrs.get('category', instance.category if instance else None)

        if category and not category.is_active:
            raise serializers.ValidationError({'category': 'La categoria seleccionada esta inactiva.'})

        if geometry is None:
            raise serializers.ValidationError({'geometry': 'La geometria es obligatoria.'})

        try:
            summary = validate_geojson_geometry(geometry, allowed_geometry_type=category.geometry_type if category else 'ANY')
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'geometry': exc.messages})

        attrs['geometry_type'] = summary.geometry_type
        attrs['bbox'] = list(summary.bbox)
        attrs['min_lng'], attrs['min_lat'], attrs['max_lng'], attrs['max_lat'] = summary.bbox
        attrs['center_lng'], attrs['center_lat'] = summary.center
        attrs['vertex_count'] = summary.vertex_count
        attrs['length_m'] = summary.length_m
        attrs['perimeter_m'] = summary.perimeter_m
        attrs['area_m2'] = summary.area_m2
        return attrs


class GeoAssetMapSerializer(serializers.ModelSerializer):
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_color = serializers.CharField(source='category.color', read_only=True)
    category_icon = serializers.CharField(source='category.icon', read_only=True)
    parcela_code = serializers.CharField(source='parcela.codigo_parcela', read_only=True)

    class Meta:
        model = GeoAsset
        fields = [
            'id',
            'title',
            'code',
            'category',
            'category_slug',
            'category_name',
            'category_color',
            'category_icon',
            'geometry_type',
            'geometry',
            'operational_status',
            'criticality',
            'parcela',
            'parcela_code',
            'bbox',
            'center_lat',
            'center_lng',
            'length_m',
            'perimeter_m',
            'area_m2',
            'vertex_count',
            'updated_at',
        ]


class GeoAssetChoicesSerializer(serializers.Serializer):
    statuses = serializers.DictField(child=serializers.CharField())
    criticalities = serializers.DictField(child=serializers.CharField())


def geo_asset_choice_payload():
    return {
        'statuses': {value: label for value, label in GeoAssetStatus.choices},
        'criticalities': {value: label for value, label in GeoAssetCriticality.choices},
    }
