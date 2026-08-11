from rest_framework import viewsets

from apps.accounts.models import UserRole
from apps.core.permissions import RoleBasedActionPermission
from apps.core.viewsets import CachedModelViewSet
from apps.vehicles.models import Vehicle
from apps.vehicles.serializers import VehicleSerializer


class VehicleViewSet(CachedModelViewSet):
    queryset = Vehicle.objects.select_related('parcela', 'persona').all()
    serializer_class = VehicleSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['ppu_normalizado', 'parcela__codigo_parcela', 'marca', 'modelo']
    filterset_fields = ['parcela', 'tipo', 'activo']
    ordering_fields = ['created_at', 'ppu_normalizado', 'marca']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

