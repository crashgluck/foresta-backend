from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Prefetch
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserRole
from apps.access_control.models import AccessRecord
from apps.core.cache_utils import request_cache_key
from apps.core.parcel_display import primary_owner_prefetch
from apps.core.permissions import RoleBasedActionPermission, has_role_at_least
from apps.maps_app.models import Objective, ParcelMapGeometry, Visit
from apps.maps_app.serializers import ObjectiveSerializer, ParcelMapItemSerializer, ParcelOptionSerializer, VisitSerializer
from apps.parcels.models import Parcel
from apps.people.models import OwnershipType, ParcelOwnership


class ObjectiveViewSet(viewsets.ModelViewSet):
    queryset = Objective.objects.select_related('parcela', 'persona', 'assigned_to').prefetch_related(primary_owner_prefetch())
    serializer_class = ObjectiveSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['title', 'description', 'parcela__codigo_parcela', 'persona__nombre_completo']
    filterset_fields = ['status', 'parcela', 'assigned_to']
    ordering_fields = ['due_date', 'created_at', 'status']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        overdue = self.request.query_params.get('overdue')
        if overdue == 'true':
            queryset = queryset.filter(due_date__lt=timezone.now().date()).exclude(status='completed')
        return queryset


class VisitViewSet(viewsets.ModelViewSet):
    queryset = Visit.objects.select_related('parcela', 'persona', 'objective', 'admitted_by').prefetch_related(primary_owner_prefetch())
    serializer_class = VisitSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['visitor_name', 'visitor_rut', 'vehicle_plate', 'purpose', 'parcela__codigo_parcela']
    filterset_fields = ['parcela', 'objective', 'visit_datetime']
    ordering_fields = ['visit_datetime', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

    def perform_create(self, serializer):
        serializer.save(admitted_by=self.request.user)


class OwnersMapView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not has_role_at_least(request.user, UserRole.CONSULTA):
            return Response({'detail': 'No autorizado'}, status=403)

        include_inactive = request.query_params.get('include_inactive') == 'true'
        cache_key = f'maps:owners:{int(include_inactive)}'
        if settings.MAPS_OWNERS_CACHE_SECONDS:
            cached_payload = cache.get(cache_key)
            if cached_payload is not None:
                return Response(cached_payload)

        queryset = (
            ParcelMapGeometry.objects.select_related('parcela')
            .prefetch_related(
                # Para el mapa solo necesitamos el propietario principal activo.
                Prefetch(
                    'parcela__ownerships',
                    queryset=ParcelOwnership.objects.select_related('persona').filter(
                        tipo=OwnershipType.PRINCIPAL, is_active=True, is_deleted=False
                    ),
                    to_attr='map_primary_ownerships',
                )
            )
            .exclude(coordinates__isnull=True)
        )
        if not include_inactive:
            queryset = queryset.filter(parcela__estado='ACTIVA')
        serializer = ParcelMapItemSerializer(queryset, many=True)
        payload = serializer.data
        if settings.MAPS_OWNERS_CACHE_SECONDS:
            cache.set(cache_key, payload, timeout=settings.MAPS_OWNERS_CACHE_SECONDS)
        return Response(payload)


class ParcelVisitSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not has_role_at_least(request.user, UserRole.CONSULTA):
            return Response({'detail': 'No autorizado'}, status=403)

        window = (request.query_params.get('window') or 'all').strip().lower()
        cache_timeout = settings.MAPS_VISIT_SUMMARY_CACHE_SECONDS
        cache_key = request_cache_key('maps:visit-summary', request)
        if cache_timeout:
            cached_payload = cache.get(cache_key)
            if cached_payload is not None:
                return Response(cached_payload)

        visits_qs = Visit.objects.select_related('parcela').exclude(parcela_id=None)
        access_qs = AccessRecord.objects.select_related('parcela').exclude(parcela_id=None)

        today = timezone.localdate()
        if window == 'today':
            visits_qs = visits_qs.filter(visit_datetime__date=today)
            access_qs = access_qs.filter(access_datetime__date=today)
        elif window == 'week':
            visits_qs = visits_qs.filter(visit_datetime__date__gte=today - timedelta(days=6))
            access_qs = access_qs.filter(access_datetime__date__gte=today - timedelta(days=6))
        elif window == 'month':
            visits_qs = visits_qs.filter(visit_datetime__date__gte=today.replace(day=1))
            access_qs = access_qs.filter(access_datetime__date__gte=today.replace(day=1))

        summary: dict[int, dict] = {}
        counters_visits = {
            row['parcela_id']: row['total']
            for row in visits_qs.values('parcela_id').annotate(total=Count('id'))
        }
        counters_access = {
            row['parcela_id']: row['total']
            for row in access_qs.values('parcela_id').annotate(total=Count('id'))
        }

        for parcel_id in set(counters_visits.keys()) | set(counters_access.keys()):
            summary[parcel_id] = {
                'parcela_id': parcel_id,
                'visits_count': counters_visits.get(parcel_id, 0) + counters_access.get(parcel_id, 0),
                'visit_records_count': counters_visits.get(parcel_id, 0),
                'access_records_count': counters_access.get(parcel_id, 0),
                'last_visit_datetime': None,
                'last_visitor_name': '',
                'last_visitor_rut': '',
                'last_purpose': '',
                'last_vehicle_plate': '',
                'last_notes': '',
                'last_source': '',
            }

        def _merge_event(parcel_id, dt, name, rut, purpose, plate, notes, source):
            if parcel_id not in summary:
                return
            current_dt = summary[parcel_id]['last_visit_datetime']
            if current_dt is None or dt > current_dt:
                summary[parcel_id]['last_visit_datetime'] = dt
                summary[parcel_id]['last_visitor_name'] = name or ''
                summary[parcel_id]['last_visitor_rut'] = rut or ''
                summary[parcel_id]['last_purpose'] = purpose or ''
                summary[parcel_id]['last_vehicle_plate'] = plate or ''
                summary[parcel_id]['last_notes'] = notes or ''
                summary[parcel_id]['last_source'] = source

        seen_visit_parcels: set[int] = set()
        for visit in visits_qs.order_by('parcela_id', '-visit_datetime').values(
            'parcela_id',
            'visit_datetime',
            'visitor_name',
            'visitor_rut',
            'purpose',
            'vehicle_plate',
            'notes',
        ).iterator():
            parcel_id = visit['parcela_id']
            if parcel_id in seen_visit_parcels:
                continue
            seen_visit_parcels.add(parcel_id)
            _merge_event(
                parcel_id,
                visit['visit_datetime'],
                visit['visitor_name'],
                visit['visitor_rut'],
                visit['purpose'],
                visit['vehicle_plate'],
                visit['notes'],
                'visit',
            )

        seen_access_parcels: set[int] = set()
        for access in access_qs.order_by('parcela_id', '-access_datetime').values(
            'parcela_id',
            'access_datetime',
            'full_name',
            'rut',
            'motive',
            'plate',
            'note',
        ).iterator():
            parcel_id = access['parcela_id']
            if parcel_id in seen_access_parcels:
                continue
            seen_access_parcels.add(parcel_id)
            _merge_event(
                parcel_id,
                access['access_datetime'],
                access['full_name'],
                access['rut'],
                access['motive'],
                access['plate'],
                access['note'],
                'access',
            )

        ordered_summary = sorted(summary.values(), key=lambda item: item['last_visit_datetime'] or timezone.now(), reverse=True)
        if cache_timeout:
            cache.set(cache_key, ordered_summary, timeout=cache_timeout)
        return Response(ordered_summary)


class ParcelOptionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not has_role_at_least(request.user, UserRole.CONSULTA):
            return Response({'detail': 'No autorizado'}, status=403)

        include_inactive = request.query_params.get('include_inactive') == 'true'
        cache_timeout = settings.MAPS_OPTIONS_CACHE_SECONDS
        cache_key = request_cache_key('maps:parcel-options', request)
        if cache_timeout:
            cached_payload = cache.get(cache_key)
            if cached_payload is not None:
                return Response(cached_payload)

        queryset = Parcel.objects.prefetch_related(primary_owner_prefetch('ownerships')).all()
        if not include_inactive:
            queryset = queryset.filter(estado='ACTIVA')
        serializer = ParcelOptionSerializer(queryset, many=True)
        payload = serializer.data
        if cache_timeout:
            cache.set(cache_key, payload, timeout=cache_timeout)
        return Response(payload)
