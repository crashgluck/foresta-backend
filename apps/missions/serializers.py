from rest_framework import serializers

from apps.missions.models import DroneFlight, DroneMissionCode, Mission, MissionReport
from apps.parcels.models import Parcel
from apps.people.models import Person
from apps.core.parcel_display import get_parcel_owner_display

DRONE_BATTERIES_BY_TEAM = {
    'SENTRY_32': {'EA1028V', 'EA104S3', 'EA109XT', 'EA108HD', 'EA104VG'},
    'SENTRY_33': {'EA1028V', 'EA104S3', 'EA109XT', 'EA108HD', 'EA104VG'},
    'SENTRY_ENTERPRISE_30': {'ENTERPRISE', '5341464', '63602FG', '63603P7'},
    'SENTRY_ZOOM_31': {'534145B', '6360002', '641L4BM'},
}


DRONE_MISSION_CODES = {choice.value for choice in DroneMissionCode}


class MissionSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(source='parcela', queryset=Parcel.objects.all(), required=False, allow_null=True)
    persona_id = serializers.PrimaryKeyRelatedField(source='persona', queryset=Person.objects.all(), required=False, allow_null=True)
    owner_display = serializers.SerializerMethodField()
    owner_parcel_code = serializers.SerializerMethodField()
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)

    class Meta:
        model = Mission
        fields = [
            'id',
            'title',
            'description',
            'mission_type',
            'owner',
            'owner_display',
            'owner_parcel_code',
            'persona_id',
            'team_name',
            'assigned_to',
            'assigned_to_username',
            'status',
            'scheduled_for',
            'started_at',
            'completed_at',
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


class DroneFlightSerializer(serializers.ModelSerializer):
    pilot_username = serializers.CharField(source='pilot.username', read_only=True)
    team_code_label = serializers.CharField(source='get_team_code_display', read_only=True)

    class Meta:
        model = DroneFlight
        fields = [
            'id',
            'pilot',
            'pilot_username',
            'flight_datetime',
            'mission_code',
            'team_code',
            'team_code_label',
            'battery_code',
            'takeoff_platform',
            'notes',
            'legacy_source_id',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['pilot', 'pilot_username', 'team_code_label', 'legacy_source_id', 'created_at', 'updated_at']

    def validate(self, attrs):
        team_code = attrs.get('team_code') or getattr(self.instance, 'team_code', '')
        battery_code = attrs.get('battery_code') or getattr(self.instance, 'battery_code', '')

        if not team_code:
            raise serializers.ValidationError({'team_code': 'Selecciona un equipo.'})
        mission_code = attrs.get('mission_code') or getattr(self.instance, 'mission_code', '')
        if not mission_code:
            raise serializers.ValidationError({'mission_code': 'Selecciona un codigo de mision.'})
        if mission_code not in DRONE_MISSION_CODES:
            raise serializers.ValidationError({'mission_code': 'El codigo de mision seleccionado no es valido.'})
        if not battery_code:
            raise serializers.ValidationError({'battery_code': 'Selecciona una bateria.'})

        allowed_batteries = DRONE_BATTERIES_BY_TEAM.get(team_code, set())
        if battery_code not in allowed_batteries:
            raise serializers.ValidationError({'battery_code': 'La bateria seleccionada no corresponde al equipo.'})

        return attrs


class MissionReportSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = MissionReport
        fields = [
            'id',
            'mission',
            'created_by',
            'created_by_username',
            'report_date',
            'summary',
            'media_url',
            'media_type',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']
