from datetime import timedelta

from django.utils import timezone
from rest_framework import viewsets

from apps.accounts.models import UserActorType, UserRole
from apps.core.parcel_display import primary_owner_prefetch
from apps.core.permissions import RoleBasedActionPermission
from apps.missions.models import DroneFlight, Mission, MissionReport
from apps.missions.serializers import DroneFlightSerializer, MissionReportSerializer, MissionSerializer


class MissionViewSet(viewsets.ModelViewSet):
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


class DroneFlightViewSet(viewsets.ModelViewSet):
    queryset = DroneFlight.objects.select_related('pilot', 'parcela', 'persona').prefetch_related(primary_owner_prefetch())
    serializer_class = DroneFlightSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = [
        'mission_code',
        'team_code',
        'battery_code',
        'takeoff_platform',
        'notes',
        'pilot__username',
        'parcela__codigo_parcela',
        'persona__nombre_completo',
    ]
    filterset_fields = ['pilot', 'parcela', 'mission_code', 'team_code', 'flight_datetime']
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


class MissionReportViewSet(viewsets.ModelViewSet):
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
