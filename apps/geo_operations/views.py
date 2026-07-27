from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from rest_framework import decorators, exceptions, response, status, viewsets

from apps.accounts.models import UserRole
from apps.core.permissions import RoleBasedActionPermission
from apps.geo_operations.models import GeoAsset, GeoAssetCategory
from apps.geo_operations.serializers import (
    GeoAssetCategorySerializer,
    GeoAssetMapSerializer,
    GeoAssetSerializer,
    geo_asset_choice_payload,
)
from apps.geo_operations.services.geometry import bbox_intersects_filter, parse_bbox
from apps.geo_operations.services.kml import export_response


def _csv_values(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [item.strip() for item in str(value).split(',') if item.strip()]


class GeoAssetCategoryViewSet(viewsets.ModelViewSet):
    queryset = GeoAssetCategory.objects.annotate(assets_count=Count('assets')).all()
    serializer_class = GeoAssetCategorySerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['name', 'slug', 'description']
    filterset_fields = ['geometry_type', 'is_active']
    ordering_fields = ['sort_order', 'name', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.ADMINISTRADOR,
        'update': UserRole.ADMINISTRADOR,
        'partial_update': UserRole.ADMINISTRADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }


class GeoAssetViewSet(viewsets.ModelViewSet):
    serializer_class = GeoAssetSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['title', 'code', 'description', 'observations', 'category__name', 'parcela__codigo_parcela']
    filterset_fields = ['category', 'geometry_type', 'operational_status', 'criticality', 'is_active', 'parcela']
    ordering_fields = ['title', 'created_at', 'updated_at', 'last_inspection_date', 'criticality']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'map': UserRole.CONSULTA,
        'choices': UserRole.CONSULTA,
        'export': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

    def get_queryset(self):
        queryset = (
            GeoAsset.objects.select_related('category', 'parcela', 'created_by', 'updated_by')
            .filter(is_deleted=False)
            .order_by('category__sort_order', 'title')
        )
        return self.apply_filters(queryset)

    def apply_filters(self, queryset):
        params = self.request.query_params

        category_values = _csv_values(params.get('category') or params.get('categories'))
        if category_values:
            numeric_ids = [value for value in category_values if str(value).isdigit()]
            slugs = [value for value in category_values if not str(value).isdigit()]
            category_filter = Q()
            if numeric_ids:
                category_filter |= Q(category_id__in=numeric_ids)
            if slugs:
                category_filter |= Q(category__slug__in=slugs)
            queryset = queryset.filter(category_filter)

        for query_param, field_name in [
            ('geometry_type', 'geometry_type'),
            ('status', 'operational_status'),
            ('operational_status', 'operational_status'),
            ('criticality', 'criticality'),
        ]:
            values = _csv_values(params.get(query_param))
            if values:
                queryset = queryset.filter(**{f'{field_name}__in': values})

        is_active = params.get('is_active')
        if is_active in {'true', '1', 'yes'}:
            queryset = queryset.filter(is_active=True)
        elif is_active in {'false', '0', 'no'}:
            queryset = queryset.filter(is_active=False)

        bbox_raw = params.get('bbox')
        if bbox_raw:
            try:
                bbox = parse_bbox(bbox_raw)
            except DjangoValidationError as exc:
                raise exceptions.ValidationError({'bbox': exc.messages})
            queryset = bbox_intersects_filter(queryset, bbox)

        return queryset

    def perform_create(self, serializer):
        asset = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        self._log_change(asset, 'created')

    def perform_update(self, serializer):
        asset = serializer.save(updated_by=self.request.user)
        self._log_change(asset, 'updated')

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        instance.delete()
        self._log_change(instance, 'deleted')

    def _log_change(self, asset, action):
        asset.change_logs.create(
            user=self.request.user,
            action=action,
            snapshot={
                'title': asset.title,
                'category': asset.category.slug,
                'geometry_type': asset.geometry_type,
                'bbox': asset.bbox,
                'status': asset.operational_status,
                'criticality': asset.criticality,
            },
        )

    @decorators.action(detail=False, methods=['get'])
    def choices(self, request):
        return response.Response(geo_asset_choice_payload())

    @decorators.action(detail=False, methods=['get'])
    def map(self, request):
        queryset = self.filter_queryset(self.get_queryset())[:1000]
        serializer = GeoAssetMapSerializer(queryset, many=True)
        return response.Response(serializer.data)

    @decorators.action(detail=False, methods=['get'])
    def export(self, request):
        export_format = (request.query_params.get('file_format') or request.query_params.get('export_format') or 'kml').lower()
        if export_format not in {'kml', 'kmz'}:
            return response.Response({'detail': 'Formato no soportado. Usa kml o kmz.'}, status=status.HTTP_400_BAD_REQUEST)

        queryset = self.filter_queryset(self.get_queryset())
        ids = _csv_values(request.query_params.get('ids'))
        if ids:
            queryset = queryset.filter(id__in=[value for value in ids if str(value).isdigit()])
        queryset = queryset[:2000]

        return export_response(queryset, file_stem='foresta-infraestructura', export_format=export_format)
