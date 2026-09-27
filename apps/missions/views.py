from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import UserActorType, UserRole
from apps.core.parcel_display import primary_owner_prefetch
from apps.core.permissions import RoleBasedActionPermission
from apps.core.viewsets import CachedModelViewSet
from apps.missions.models import DroneFlight, Mission, MissionReport
from apps.missions.serializers import DroneFlightSerializer, MissionReportSerializer, MissionSerializer


RECO_MISSION_CODES = [f'RECO {number}' for number in range(1, 8)]


class MissionViewSet(CachedModelViewSet):
    queryset = Mission.objects.select_related('parcela', 'persona', 'assigned_to').prefetch_related(primary_owner_prefetch())
    serializer_class = MissionSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['title', 'description', 'mission_type', 'team_name', 'parcela__codigo_parcela', 'persona__nombre_completo']
    filterset_fields = ['status', 'mission_type', 'parcela', 'assigned_to', 'team_name']
    ordering_fields = ['scheduled_for', 'created_at', 'status']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {
        '*': [UserActorType.PORTAL_ACCESO]
    }


class DroneFlightViewSet(CachedModelViewSet):
    queryset = DroneFlight.objects.select_related('pilot')
    serializer_class = DroneFlightSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = [
        'mission_code',
        'team_code',
        'battery_code',
        'takeoff_platform',
        'notes',
        'pilot__username',
    ]
    filterset_fields = ['pilot', 'mission_code', 'team_code', 'flight_datetime']
    ordering_fields = ['flight_datetime', 'created_at', 'mission_code', 'team_code']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {
        '*': [UserActorType.PORTAL_ACCESO]
    }

    def _operator_counts(self, queryset):
        return [
            {
                'operator': (
                    row['pilot__username']
                    or row['pilot__email']
                    or 'Sin operador'
                ),
                'total': row['total'],
            }
            for row in queryset.values('pilot_id', 'pilot__username', 'pilot__email').annotate(total=Count('id')).order_by('-total', 'pilot__username')
        ]

    def _reco_breakdown(self, queryset):
        return [
            {
                'mission_code': mission_code,
                'total': mission_queryset.count(),
                'by_operator': self._operator_counts(mission_queryset),
            }
            for mission_code in RECO_MISSION_CODES
            for mission_queryset in [queryset.filter(mission_code=mission_code)]
        ]

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        reco_queryset = queryset.filter(mission_code__startswith='RECO')
        brifo_queryset = queryset.filter(mission_code='BRIFO')
        qrf_queryset = queryset.filter(mission_code='QRF')
        notes_queryset = queryset.exclude(Q(notes__isnull=True) | Q(notes=''))

        return Response(
            {
                'total': queryset.count(),
                'by_operator': self._operator_counts(queryset),
                'groups': {
                    'reco': {
                        'total': reco_queryset.count(),
                        'by_operator': self._operator_counts(reco_queryset),
                        'by_mission': self._reco_breakdown(queryset),
                    },
                    'brifo': {'total': brifo_queryset.count(), 'by_operator': self._operator_counts(brifo_queryset)},
                    'qrf': {'total': qrf_queryset.count(), 'by_operator': self._operator_counts(qrf_queryset)},
                    'notes': {'total': notes_queryset.count(), 'by_operator': self._operator_counts(notes_queryset)},
                },
            }
        )

    def get_queryset(self):
        queryset = super().get_queryset()
        period = self.request.query_params.get('period')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        team_code = self.request.query_params.get('team')
        mission_code = self.request.query_params.get('mission')
        user_id = self.request.query_params.get('user')

        today = timezone.localdate()
        if period == 'daily':
            queryset = queryset.filter(flight_datetime__date=today)
        elif period == 'weekly':
            queryset = queryset.filter(flight_datetime__date__gte=today - timedelta(days=7))
        elif period == 'monthly':
            queryset = queryset.filter(flight_datetime__date__gte=today - timedelta(days=30))

        if date_from:
            queryset = queryset.filter(flight_datetime__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(flight_datetime__date__lte=date_to)
        if team_code:
            queryset = queryset.filter(team_code__icontains=team_code)
        if mission_code:
            queryset = queryset.filter(mission_code__icontains=mission_code)
        if user_id:
            queryset = queryset.filter(pilot_id=user_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(pilot=self.request.user)

    def perform_update(self, serializer):
        pilot = serializer.instance.pilot or self.request.user
        serializer.save(pilot=pilot)


class MissionReportViewSet(CachedModelViewSet):
    queryset = MissionReport.objects.select_related('mission', 'created_by', 'mission__assigned_to')
    serializer_class = MissionReportSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['summary', 'mission__title', 'mission__team_name', 'created_by__username']
    filterset_fields = ['mission', 'media_type', 'report_date', 'created_by']
    ordering_fields = ['report_date', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {
        '*': [UserActorType.PORTAL_ACCESO]
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        period = self.request.query_params.get('period')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        team_name = self.request.query_params.get('team')
        mission_id = self.request.query_params.get('mission')
        user_id = self.request.query_params.get('user')

        today = timezone.localdate()
        if period == 'daily':
            queryset = queryset.filter(report_date=today)
        elif period == 'weekly':
            queryset = queryset.filter(report_date__gte=today - timedelta(days=7))
        elif period == 'monthly':
            queryset = queryset.filter(report_date__gte=today - timedelta(days=30))

        if date_from:
            queryset = queryset.filter(report_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(report_date__lte=date_to)
        if team_name:
            queryset = queryset.filter(mission__team_name__icontains=team_name)
        if mission_id:
            queryset = queryset.filter(mission_id=mission_id)
        if user_id:
            queryset = queryset.filter(created_by_id=user_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
