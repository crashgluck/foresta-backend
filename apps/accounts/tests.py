from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole


class AuthFlowTests(APITestCase):
    def test_register_and_login(self):
        register_payload = {
            'email': 'nuevo@example.com',
            'first_name': 'Nuevo',
            'last_name': 'Usuario',
            'password': 'ClaveSegura123',
        }
        register = self.client.post('/api/v1/auth/register/', register_payload, format='json')
        self.assertEqual(register.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email='nuevo@example.com')
        self.assertFalse(user.is_active)

        login = self.client.post('/api/v1/auth/login/', {'email': 'nuevo@example.com', 'password': 'ClaveSegura123'}, format='json')
        self.assertEqual(login.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password(self):
        user = User.objects.create_user(email='test@example.com', password='Vieja12345', role=UserRole.OPERADOR)
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': 'Vieja12345'}, format='json')
        access = login.data['access']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        response = self.client.post(
            '/api/v1/auth/change-password/',
            {'old_password': 'Vieja12345', 'new_password': 'Nueva12345'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        relogin = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': 'Nueva12345'}, format='json')
        self.assertEqual(relogin.status_code, status.HTTP_200_OK)
