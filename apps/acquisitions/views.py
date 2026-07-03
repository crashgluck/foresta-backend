from rest_framework import viewsets

from apps.accounts.models import UserRole
from apps.acquisitions.models import RFIDCard, RemoteControl, VehicleLogo
from apps.acquisitions.serializers import RFIDCardSerializer, RemoteControlSerializer, VehicleLogoSerializer
from apps.core.parcel_display import primary_owner_prefetch
from apps.core.permissions import RoleBasedActionPermission


class RemoteControlViewSet(viewsets.ModelViewSet):
    queryset = RemoteControl.objects.select_related('parcela', 'persona').prefetch_related(primary_owner_prefetch())
    serializer_class = RemoteControlSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['serial_number', 'model', 'parcela__codigo_parcela', 'persona__nombre_completo']
    filterset_fields = ['status', 'parcela', 'issued_at']
    ordering_fields = ['serial_number', 'issued_at', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }


class RFIDCardViewSet(viewsets.ModelViewSet):
    queryset = RFIDCard.objects.select_related('parcela', 'persona').prefetch_related(primary_owner_prefetch())
    serializer_class = RFIDCardSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['uid', 'color', 'parcela__codigo_parcela', 'persona__nombre_completo']
    filterset_fields = ['status', 'parcela', 'issued_at']
    ordering_fields = ['uid', 'issued_at', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }


class VehicleLogoViewSet(viewsets.ModelViewSet):
    queryset = VehicleLogo.objects.select_related('parcela', 'persona').prefetch_related(primary_owner_prefetch())
    serializer_class = VehicleLogoSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['plate', 'logo_code', 'parcela__codigo_parcela', 'persona__nombre_completo']
    filterset_fields = ['status', 'parcela', 'issued_at']
    ordering_fields = ['plate', 'issued_at', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

