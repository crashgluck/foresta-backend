from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserRole
from apps.core.permissions import has_role_at_least
from apps.iot.services.nodotech import NodotechClient, NodotechClientError
from apps.iot.serializers import RelayPulseSerializer


def nodotech_error_response(exc: NodotechClientError) -> Response:
    upstream_status = exc.status_code or status.HTTP_502_BAD_GATEWAY
    if not getattr(exc, 'upstream', True):
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE
    elif upstream_status in {status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND}:
        response_status = upstream_status
    elif upstream_status == status.HTTP_504_GATEWAY_TIMEOUT:
        response_status = status.HTTP_504_GATEWAY_TIMEOUT
    else:
        response_status = status.HTTP_502_BAD_GATEWAY

    code = (
        'NODOTECH_CONFIGURATION_ERROR'
        if not getattr(exc, 'upstream', True)
        else 'NODOTECH_UPSTREAM_ERROR'
    )
    return Response(
        {
            'ok': False,
            'code': code,
            'detail': exc.message,
            'details': exc.details,
        },
        status=response_status,
    )


class NodotechComponentListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not has_role_at_least(request.user, UserRole.CONSULTA):
            return Response({'ok': False, 'detail': 'No autorizado'}, status=403)

        try:
            components = NodotechClient().list_components()
        except NodotechClientError as exc:
            return nodotech_error_response(exc)

        return Response({'ok': True, 'components': components})


class NodotechRelayCommandView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    action_name = ''

    def post(self, request, component_id: int):
        if not has_role_at_least(request.user, UserRole.OPERADOR):
            return Response({'ok': False, 'detail': 'No autorizado'}, status=403)

        serializer = RelayPulseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = self.build_payload(serializer.validated_data)
        try:
            command = NodotechClient().command_component(component_id, payload)
        except NodotechClientError as exc:
            return nodotech_error_response(exc)

        return Response(
            {
                'ok': True,
                'action': self.action_name,
                'component_id': component_id,
                'nodotech_response': command,
            },
            status=status.HTTP_201_CREATED,
        )

    def build_payload(self, validated_data):
        raise NotImplementedError


class NodotechRelayOnView(NodotechRelayCommandView):
    action_name = 'on'

    def build_payload(self, validated_data):
        return {
            'command': 'SET_RELAY',
            'desired_state': 'ON',
        }


class NodotechRelayOffView(NodotechRelayCommandView):
    action_name = 'off'

    def build_payload(self, validated_data):
        return {
            'command': 'SET_RELAY',
            'desired_state': 'OFF',
        }


class NodotechRelayPulseView(NodotechRelayCommandView):
    action_name = 'pulse'

    def build_payload(self, validated_data):
        return {
            'command': 'PULSE_RELAY',
            'pulse_ms': validated_data.get(
                'pulse_ms',
                getattr(settings, 'NODOTECH_DEFAULT_PULSE_MS', 700),
            ),
        }
