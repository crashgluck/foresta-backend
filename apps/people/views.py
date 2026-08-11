from rest_framework import viewsets

from apps.accounts.models import UserActorType, UserRole
from apps.core.permissions import RoleBasedActionPermission
from apps.core.viewsets import CachedModelViewSet
from apps.people.models import ParcelOwnership, ParcelResident, Person
from apps.people.serializers import ParcelOwnershipSerializer, ParcelResidentSerializer, PersonSerializer


class PersonViewSet(CachedModelViewSet):
    queryset = Person.objects.all().order_by('nombre_completo')
    serializer_class = PersonSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['nombre_completo', 'rut_normalizado', 'email', 'telefono_principal']
    filterset_fields = ['activo']
    ordering_fields = ['nombre_completo', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {
        '*': [UserActorType.PORTAL_ACCESO, UserActorType.OPERADOR_DRONE]
    }


class ParcelOwnershipViewSet(CachedModelViewSet):
    queryset = ParcelOwnership.objects.select_related('parcela', 'persona').all()
    serializer_class = ParcelOwnershipSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['parcela__codigo_parcela', 'persona__nombre_completo', 'persona__rut_normalizado']
    filterset_fields = ['tipo', 'is_active', 'parcela']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {
        '*': [UserActorType.PORTAL_ACCESO, UserActorType.OPERADOR_DRONE]
    }


class ParcelResidentViewSet(CachedModelViewSet):
    queryset = ParcelResident.objects.select_related('parcela', 'persona').all()
    serializer_class = ParcelResidentSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['parcela__codigo_parcela', 'persona__nombre_completo']
    filterset_fields = ['tipo_residencia', 'is_active', 'parcela']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {
        '*': [UserActorType.PORTAL_ACCESO, UserActorType.OPERADOR_DRONE]
    }

