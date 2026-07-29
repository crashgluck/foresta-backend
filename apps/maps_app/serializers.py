from rest_framework import serializers

from apps.core.parcel_display import get_parcel_owner_display, get_primary_owner_for_parcel
from apps.maps_app.models import Objective, ParcelMapGeometry, Visit
from apps.parcels.models import Parcel, ParcelStatus
from apps.people.models import Person


class ObjectiveSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(source='parcela', queryset=Parcel.objects.all(), required=False, allow_null=True)
    persona_id = serializers.PrimaryKeyRelatedField(source='persona', queryset=Person.objects.all(), required=False, allow_null=True)
    owner_display = serializers.SerializerMethodField()
    owner_parcel_code = serializers.SerializerMethodField()
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)

    class Meta:
        model = Objective
        fields = [
            'id',
            'owner',
            'owner_display',
            'owner_parcel_code',
            'persona_id',
            'assigned_to',
            'assigned_to_username',
            'title',
            'description',
            'latitude',
            'longitude',
            'coordinates',
            'color',
            'due_date',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_owner_parcel_code(self, obj):
        code, _ = get_parcel_owner_display(obj.parcela)
        return code

    def get_owner_display(self, obj):
        _, display = get_parcel_owner_display(obj.parcela)
        return display


class VisitSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(source='parcela', queryset=Parcel.objects.all())
    persona_id = serializers.PrimaryKeyRelatedField(source='persona', queryset=Person.objects.all(), required=False, allow_null=True)
    owner_display = serializers.SerializerMethodField()
    owner_parcel_code = serializers.SerializerMethodField()

    class Meta:
        model = Visit
        fields = [
            'id',
            'owner',
            'owner_display',
            'owner_parcel_code',
            'persona_id',
            'objective',
            'visitor_name',
            'visitor_rut',
            'vehicle_plate',
            'purpose',
            'visit_datetime',
            'notes',
            'admitted_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['admitted_by', 'created_at', 'updated_at']

    def get_owner_parcel_code(self, obj):
        code, _ = get_parcel_owner_display(obj.parcela)
        return code

    def get_owner_display(self, obj):
        _, display = get_parcel_owner_display(obj.parcela)
        return display


class ParcelMapItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='parcela_id', read_only=True)
    lote = serializers.CharField(source='parcela.letra_lote', read_only=True)
    n_lote = serializers.SerializerMethodField()
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    rut = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    secondary_email = serializers.SerializerMethodField()
    secondary_phone_1 = serializers.SerializerMethodField()
    secondary_phone_2 = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    parcel_code = serializers.CharField(source='parcela.codigo_parcela', read_only=True)

    class Meta:
        model = ParcelMapGeometry
        fields = [
            'id',
            'parcel_code',
            'lote',
            'n_lote',
            'first_name',
            'last_name',
            'rut',
            'email',
            'secondary_email',
            'secondary_phone_1',
            'secondary_phone_2',
            'coordinates',
            'color',
            'is_active',
        ]

    def _primary_owner(self, obj):
        parcel = obj.parcela
        if hasattr(parcel, '_map_cached_primary_owner'):
            return getattr(parcel, '_map_cached_primary_owner')

        owner = get_primary_owner_for_parcel(parcel)
        setattr(parcel, '_map_cached_primary_owner', owner)
        return owner

    def get_n_lote(self, obj):
        suffix = obj.parcela.sufijo_lote or ''
        if obj.parcela.numero_lote is None:
            return ''
        return f'{obj.parcela.numero_lote}{suffix}'

    def get_first_name(self, obj):
        person = self._primary_owner(obj)
        if not person:
            return ''
        if person.nombres:
            return person.nombres
        return (person.nombre_completo or '').split(' ')[0]

    def get_last_name(self, obj):
        person = self._primary_owner(obj)
        if not person:
            return ''
        if person.apellidos:
            return person.apellidos
        parts = (person.nombre_completo or '').split(' ')
        return ' '.join(parts[1:]) if len(parts) > 1 else ''

    def get_rut(self, obj):
        person = self._primary_owner(obj)
        return person.rut if person else ''

    def get_email(self, obj):
        person = self._primary_owner(obj)
        return person.email if person else ''

    def get_secondary_email(self, obj):
        return ''

    def get_secondary_phone_1(self, obj):
        person = self._primary_owner(obj)
        return person.telefono_principal if person else ''

    def get_secondary_phone_2(self, obj):
        person = self._primary_owner(obj)
        return person.telefono_secundario if person else ''

    def get_is_active(self, obj):
        return obj.parcela.estado == ParcelStatus.ACTIVA


class ParcelMapPublicItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='parcela_id', read_only=True)
    lote = serializers.CharField(source='parcela.letra_lote', read_only=True)
    n_lote = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    parcel_code = serializers.CharField(source='parcela.codigo_parcela', read_only=True)

    class Meta:
        model = ParcelMapGeometry
        fields = [
            'id',
            'parcel_code',
            'lote',
            'n_lote',
            'coordinates',
            'color',
            'is_active',
        ]

    def get_n_lote(self, obj):
        suffix = obj.parcela.sufijo_lote or ''
        if obj.parcela.numero_lote is None:
            return ''
        return f'{obj.parcela.numero_lote}{suffix}'

    def get_is_active(self, obj):
        return obj.parcela.estado == ParcelStatus.ACTIVA


class ParcelOptionSerializer(serializers.ModelSerializer):
    parcel_code = serializers.CharField(source='codigo_parcela', read_only=True)
    full_name = serializers.SerializerMethodField()
    rut = serializers.SerializerMethodField()

    class Meta:
        model = Parcel
        fields = ['id', 'parcel_code', 'full_name', 'rut']

    def _primary_owner(self, obj):
        return get_primary_owner_for_parcel(obj)

    def get_full_name(self, obj):
        person = self._primary_owner(obj)
        return person.nombre_completo if person else ''

    def get_rut(self, obj):
        person = self._primary_owner(obj)
        return person.rut if person else ''


class ParcelCodeOptionSerializer(serializers.ModelSerializer):
    parcel_code = serializers.CharField(source='codigo_parcela', read_only=True)

    class Meta:
        model = Parcel
        fields = ['id', 'parcel_code']
