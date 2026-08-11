from django.db.models import Q
from rest_framework import decorators, response, viewsets

from apps.accounts.models import UserActorType, UserRole
from apps.core.normalizers import normalize_parcel_code
from apps.core.permissions import RoleBasedActionPermission
from apps.core.viewsets import CachedModelViewSet
from apps.parcels.models import Parcel
from apps.parcels.serializers import ParcelConsolidatedSerializer, ParcelSerializer


class ParcelViewSet(CachedModelViewSet):
    queryset = Parcel.objects.all()
    serializer_class = ParcelSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['codigo_parcela', 'codigo_parcela_key', 'referencia_direccion', 'observaciones_generales']
    filterset_fields = ['estado', 'letra_lote']
    ordering_fields = ['codigo_parcela_key', 'created_at', 'estado']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'consolidated': UserRole.CONSULTA,
        'consolidated_by_code': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {
        '*': [UserActorType.PORTAL_ACCESO, UserActorType.OPERADOR_DRONE]
    }

    def get_queryset(self):
        qs = super().get_queryset()
        critical = self.request.query_params.get('critical')
        if critical and critical.lower() in {'1', 'true', 'yes'}:
            qs = qs.filter(
                Q(service_cuts__activo=True)
                | Q(common_expense_debts__estado_pago__in=['PENDIENTE', 'VENCIDO'])
                | Q(service_debts__estado_pago__in=['PENDIENTE', 'VENCIDO'])
            ).distinct()
        return qs

    def get_consolidated_queryset(self):
        return (
            self.get_queryset()
            .select_related('work_status')
            .prefetch_related(
                'ownerships__persona',
                'residents__persona',
                'vehicles',
                'common_expense_debts',
                'service_debts',
                'payment_agreements',
                'unpaid_fines',
                'service_cuts',
                'service_history',
                'notes',
                'access_records',
            )
        )

    @decorators.action(detail=True, methods=['get'], url_path='ficha-consolidada')
    def consolidated(self, request, pk=None):
        parcel = self.get_consolidated_queryset().filter(pk=pk).first()
        if not parcel:
            return response.Response({'detail': 'Parcela no encontrada'}, status=404)
        serializer = ParcelConsolidatedSerializer(parcel)
        return response.Response(serializer.data)

    @decorators.action(detail=False, methods=['get'], url_path=r'by-code/(?P<codigo>[^/.]+)/ficha-consolidada')
    def consolidated_by_code(self, request, codigo=None):
        normalized_code = normalize_parcel_code(codigo) or (codigo or '').strip().upper()
        parcel = self.get_consolidated_queryset().filter(codigo_parcela_key__iexact=normalized_code).first()
        if not parcel:
            return response.Response({'detail': 'Parcela no encontrada'}, status=404)
        serializer = ParcelConsolidatedSerializer(parcel)
        return response.Response(serializer.data)

