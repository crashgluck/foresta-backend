from rest_framework import viewsets

from apps.accounts.models import UserRole
from apps.core.permissions import RoleBasedActionPermission
from apps.core.viewsets import CachedModelViewSet
from apps.utilities.models import ServiceCut, ServiceHistory
from apps.utilities.serializers import ServiceCutSerializer, ServiceHistorySerializer


class ServiceCutViewSet(CachedModelViewSet):
    queryset = ServiceCut.objects.select_related('parcela').all()
    serializer_class = ServiceCutSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['parcela__codigo_parcela', 'estado', 'motivo', 'sello']
    filterset_fields = ['parcela', 'tipo_corte', 'activo']
    ordering_fields = ['fecha', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }


class ServiceHistoryViewSet(CachedModelViewSet):
    queryset = ServiceHistory.objects.select_related('parcela').all()
    serializer_class = ServiceHistorySerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['parcela__codigo_parcela', 'numero_orden', 'descripcion', 'solicitante']
    filterset_fields = ['parcela', 'resultado']
    ordering_fields = ['fecha_ingreso', 'fecha_ejecucion', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

