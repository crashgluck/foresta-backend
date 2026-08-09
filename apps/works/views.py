from rest_framework import viewsets

from apps.accounts.models import UserRole
from apps.core.permissions import RoleBasedActionPermission
from apps.core.viewsets import CachedModelViewSet
from apps.works.models import ParcelWorkStatus
from apps.works.serializers import ParcelWorkStatusSerializer


class ParcelWorkStatusViewSet(CachedModelViewSet):
    queryset = ParcelWorkStatus.objects.select_related('parcela').all()
    serializer_class = ParcelWorkStatusSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['parcela__codigo_parcela', 'estado_actual', 'rol_sii']
    filterset_fields = ['foco_incendio', 'kpi', 'parcela']
    ordering_fields = ['created_at', 'atributo_kpi']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

