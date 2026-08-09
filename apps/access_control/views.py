from rest_framework import viewsets

from apps.access_control.models import AccessRecord, BlacklistEntry
from apps.access_control.serializers import AccessRecordSerializer, BlacklistEntrySerializer
from apps.accounts.models import UserActorType, UserRole
from apps.core.parcel_display import primary_owner_prefetch
from apps.core.permissions import RoleBasedActionPermission
from apps.core.viewsets import CachedModelViewSet


class BlacklistEntryViewSet(CachedModelViewSet):
    queryset = BlacklistEntry.objects.all()
    serializer_class = BlacklistEntrySerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['rut', 'plate', 'reason']
    filterset_fields = ['is_active']
    ordering_fields = ['created_at', 'updated_at', 'rut', 'plate']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {
        '*': [UserActorType.OPERADOR_DRONE]
    }


class AccessRecordViewSet(CachedModelViewSet):
    queryset = AccessRecord.objects.select_related('parcela', 'persona', 'created_by', 'updated_by').prefetch_related(primary_owner_prefetch())
    serializer_class = AccessRecordSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['full_name', 'rut', 'plate', 'motive', 'company_name', 'parcela__codigo_parcela', 'persona__nombre_completo']
    filterset_fields = ['status', 'source', 'parcela', 'access_datetime']
    ordering_fields = ['access_datetime', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {
        '*': [UserActorType.OPERADOR_DRONE]
    }
