from rest_framework import serializers


class RelayPulseSerializer(serializers.Serializer):
    pulse_ms = serializers.IntegerField(required=False, min_value=1, max_value=5000)


class NodotechCommandResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    command = serializers.JSONField(required=False)
    nodotech_response = serializers.JSONField(required=False)
