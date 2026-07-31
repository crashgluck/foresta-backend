import json

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.geo_operations.models import (
    GeoAsset,
    GeoAssetCategory,
    GeoAssetCriticality,
    GeoServiceType,
    GeoAssetStatus,
)
from apps.geo_operations.services.geometry import validate_geojson_geometry
from apps.geo_operations.services.images import process_geo_asset_photo
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
            'service_type',
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
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_color = serializers.CharField(source='category.color', read_only=True)
    category_icon = serializers.CharField(source='category.icon', read_only=True)
    category_service_type = serializers.CharField(source='category.service_type', read_only=True)
    parcela_code = serializers.CharField(source='parcela.codigo_parcela', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    updated_by_name = serializers.CharField(source='updated_by.full_name', read_only=True)
    parcela = serializers.PrimaryKeyRelatedField(queryset=Parcel.objects.all(), required=False, allow_null=True)
    photo_upload = serializers.FileField(write_only=True, required=False, allow_empty_file=False)
    remove_photo = serializers.BooleanField(write_only=True, required=False, default=False)
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = GeoAsset
        fields = [
            'id',
            'title',
            'code',
            'category',
            'category_detail',
            'category_slug',
            'category_name',
            'category_color',
            'category_icon',
            'category_service_type',
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
            'photo',
            'photo_url',
            'photo_upload',
            'remove_photo',
            'photo_original_name',
            'photo_content_type',
            'photo_size',
            'photo_width',
            'photo_height',
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
            'photo',
            'photo_original_name',
            'photo_content_type',
            'photo_size',
            'photo_width',
            'photo_height',
            'created_at',
            'updated_at',
        ]

    def get_photo_url(self, obj):
        if not obj.photo:
            return ''
        request = self.context.get('request')
        url = obj.photo.url
        return request.build_absolute_uri(url) if request else url

    def _parse_json_value(self, attrs, field_name, fallback=None):
        if field_name not in attrs:
            return fallback
        value = attrs.get(field_name)
        if value is None or value == '':
            return fallback
        if isinstance(value, str):
            try:
                attrs[field_name] = json.loads(value)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError({field_name: 'Debe ser JSON valido.'}) from exc
        return attrs.get(field_name)

    def validate(self, attrs):
        instance = self.instance
        self._parse_json_value(attrs, 'geometry', instance.geometry if instance else None)
        self._parse_json_value(attrs, 'properties', {})
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

    def _apply_photo(self, asset, uploaded_file):
        processed = process_geo_asset_photo(uploaded_file)
        if asset.photo:
            asset.photo.delete(save=False)
        asset.photo.save(processed.filename, processed.content, save=False)
        asset.photo_original_name = processed.original_name
        asset.photo_content_type = processed.content_type
        asset.photo_size = processed.size
        asset.photo_width = processed.width
        asset.photo_height = processed.height

    def _clear_photo(self, asset):
        if asset.photo:
            asset.photo.delete(save=False)
        asset.photo = ''
        asset.photo_original_name = ''
        asset.photo_content_type = ''
        asset.photo_size = 0
        asset.photo_width = 0
        asset.photo_height = 0

    def create(self, validated_data):
        uploaded_file = validated_data.pop('photo_upload', None)
        validated_data.pop('remove_photo', None)
        asset = GeoAsset(**validated_data)
        if uploaded_file:
            self._apply_photo(asset, uploaded_file)
        asset.save()
        return asset

    def update(self, instance, validated_data):
        uploaded_file = validated_data.pop('photo_upload', None)
        remove_photo = validated_data.pop('remove_photo', False)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if remove_photo:
            self._clear_photo(instance)
        if uploaded_file:
            self._apply_photo(instance, uploaded_file)
        instance.save()
        return instance


class GeoAssetMapSerializer(serializers.ModelSerializer):
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_color = serializers.CharField(source='category.color', read_only=True)
    category_icon = serializers.CharField(source='category.icon', read_only=True)
    category_service_type = serializers.CharField(source='category.service_type', read_only=True)
    parcela_code = serializers.CharField(source='parcela.codigo_parcela', read_only=True)
    photo_url = serializers.SerializerMethodField()

    def get_photo_url(self, obj):
        if not obj.photo:
            return ''
        request = self.context.get('request')
        url = obj.photo.url
        return request.build_absolute_uri(url) if request else url

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
            'category_service_type',
            'geometry_type',
            'geometry',
            'properties',
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
            'photo_url',
            'photo_width',
            'photo_height',
            'updated_at',
        ]


class GeoAssetChoicesSerializer(serializers.Serializer):
    statuses = serializers.DictField(child=serializers.CharField())
    criticalities = serializers.DictField(child=serializers.CharField())


def geo_asset_choice_payload():
    return {
        'statuses': {value: label for value, label in GeoAssetStatus.choices},
        'criticalities': {value: label for value, label in GeoAssetCriticality.choices},
        'service_types': {value: label for value, label in GeoServiceType.choices},
    }
