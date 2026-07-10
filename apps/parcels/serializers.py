from rest_framework import serializers

from apps.finance.serializers import (
    CommonExpenseDebtSerializer,
    PaymentAgreementSerializer,
    ServiceDebtSerializer,
    UnpaidFineSerializer,
)
from apps.access_control.serializers import AccessRecordSerializer
from apps.notes.serializers import AdministrativeNoteSerializer
from apps.parcels.models import Parcel
from apps.people.serializers import ParcelOwnershipSerializer, ParcelResidentSerializer
from apps.utilities.serializers import ServiceCutSerializer, ServiceHistorySerializer
from apps.vehicles.serializers import VehicleSerializer
from apps.works.serializers import ParcelWorkStatusSerializer


PARCEL_BASE_FIELDS = [
    'id',
    'codigo_parcela',
    'codigo_parcela_key',
    'letra_lote',
    'numero_lote',
    'sufijo_lote',
    'estado',
    'referencia_direccion',
    'observaciones_generales',
    'created_at',
    'updated_at',
]


class ParcelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parcel
        fields = PARCEL_BASE_FIELDS
        read_only_fields = ('codigo_parcela_key', 'letra_lote', 'numero_lote', 'sufijo_lote', 'created_at', 'updated_at')


class ParcelConsolidatedSerializer(ParcelSerializer):
    owners = serializers.SerializerMethodField()
    residents = ParcelResidentSerializer(many=True, read_only=True)
    vehicles = VehicleSerializer(many=True, read_only=True)
    common_expense_debts = CommonExpenseDebtSerializer(many=True, read_only=True)
    service_debts = ServiceDebtSerializer(many=True, read_only=True)
    payment_agreements = PaymentAgreementSerializer(many=True, read_only=True)
    unpaid_fines = UnpaidFineSerializer(many=True, read_only=True)
    service_cuts = ServiceCutSerializer(many=True, read_only=True)
    service_history = ServiceHistorySerializer(many=True, read_only=True)
    notes = AdministrativeNoteSerializer(many=True, read_only=True)
    access_records = AccessRecordSerializer(many=True, read_only=True)
    work_status = ParcelWorkStatusSerializer(read_only=True)

    class Meta(ParcelSerializer.Meta):
        fields = PARCEL_BASE_FIELDS + [
            'owners',
            'residents',
            'vehicles',
            'common_expense_debts',
            'service_debts',
            'payment_agreements',
            'unpaid_fines',
            'service_cuts',
            'service_history',
            'notes',
            'access_records',
            'work_status',
        ]

    def get_owners(self, obj):
        data = obj.ownerships.filter(is_deleted=False).select_related('persona')
        return ParcelOwnershipSerializer(data, many=True).data

