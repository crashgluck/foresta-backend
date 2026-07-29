from unittest.mock import Mock, patch

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole


class NodotechIotApiTests(APITestCase):
    def authenticate(self, role=UserRole.OPERADOR):
        user = User.objects.create_user(
            email=f'{role.lower()}@example.com',
            password='Pass123456',
            role=role,
        )
        self.client.force_authenticate(user=user)
        return user

    @patch('apps.iot.views.NodotechClient')
    def test_list_components_requires_authenticated_user(self, client_class):
        response = self.client.get('/api/v1/iot/components/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        client_class.assert_not_called()

    @patch('apps.iot.views.NodotechClient')
    def test_consulta_can_list_components(self, client_class):
        self.authenticate(UserRole.CONSULTA)
        client = Mock()
        client.list_components.return_value = [{'id': 1, 'name': 'Relay 1'}]
        client_class.return_value = client

        response = self.client.get('/api/v1/iot/components/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['components'], [{'id': 1, 'name': 'Relay 1'}])
        client.list_components.assert_called_once_with()

    @patch('apps.iot.views.NodotechClient')
    def test_consulta_cannot_send_relay_command(self, client_class):
        self.authenticate(UserRole.CONSULTA)

        response = self.client.post('/api/v1/iot/components/1/on/', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        client_class.assert_not_called()

    @patch('apps.iot.views.NodotechClient')
    def test_operator_can_turn_relay_on(self, client_class):
        self.authenticate(UserRole.OPERADOR)
        client = Mock()
        client.command_component.return_value = {'ok': True, 'command_id': 123}
        client_class.return_value = client

        response = self.client.post('/api/v1/iot/components/7/on/', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        client.command_component.assert_called_once_with(
            7,
            {
                'command': 'SET_RELAY',
                'desired_state': 'ON',
            },
        )

    @override_settings(NODOTECH_DEFAULT_PULSE_MS=900)
    @patch('apps.iot.views.NodotechClient')
    def test_operator_can_pulse_relay_with_default_duration(self, client_class):
        self.authenticate(UserRole.OPERADOR)
        client = Mock()
        client.command_component.return_value = {'ok': True, 'command_id': 123}
        client_class.return_value = client

        response = self.client.post('/api/v1/iot/components/7/pulse/', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        client.command_component.assert_called_once_with(
            7,
            {
                'command': 'PULSE_RELAY',
                'pulse_ms': 900,
            },
        )

    @override_settings(NODOTECH_DEFAULT_PULSE_MS=900)
    @patch('apps.iot.views.NodotechClient')
    def test_operator_can_pulse_relay_without_trailing_slash(self, client_class):
        self.authenticate(UserRole.OPERADOR)
        client = Mock()
        client.command_component.return_value = {'ok': True, 'command_id': 123}
        client_class.return_value = client

        response = self.client.post('/api/v1/iot/components/7/pulse', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        client.command_component.assert_called_once_with(
            7,
            {
                'command': 'PULSE_RELAY',
                'pulse_ms': 900,
            },
        )
