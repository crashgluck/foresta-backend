from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone

from apps.access_control.models import AccessRecord
from apps.accounts.models import User, UserRole
from apps.maps_app.models import ParcelMapGeometry, Visit
from apps.parcels.models import Parcel


class ParcelMapTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='map@example.com', password='Clave12345', role=UserRole.CONSULTA)
        self.parcel = Parcel.objects.create(codigo_parcela='N-19')
        ParcelMapGeometry.objects.create(parcela=self.parcel, coordinates=[[-33.45, -70.66]], color='#51ff00')

    def test_list_owner_map(self):
        login = self.client.post('/api/v1/auth/login/', {'email': self.user.email, 'password': 'Clave12345'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        response = self.client.get('/api/v1/maps/owners-map/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['parcel_code'], 'N-19')

    def test_list_owner_map_parcel_only_hides_person_fields(self):
        login = self.client.post('/api/v1/auth/login/', {'email': self.user.email, 'password': 'Clave12345'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = self.client.get('/api/v1/maps/owners-map/?parcel_only=true')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['parcel_code'], 'N-19')
        self.assertNotIn('first_name', response.data[0])
        self.assertNotIn('last_name', response.data[0])
        self.assertNotIn('rut', response.data[0])
        self.assertNotIn('email', response.data[0])
        self.assertNotIn('secondary_email', response.data[0])
        self.assertNotIn('secondary_phone_1', response.data[0])
        self.assertNotIn('secondary_phone_2', response.data[0])

    def test_parcel_options_parcel_only_hides_person_fields(self):
        login = self.client.post('/api/v1/auth/login/', {'email': self.user.email, 'password': 'Clave12345'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = self.client.get('/api/v1/maps/parcel-options/?parcel_only=true')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['parcel_code'], 'N-19')
        self.assertNotIn('full_name', response.data[0])
        self.assertNotIn('rut', response.data[0])

    def test_visit_summary(self):
        login = self.client.post('/api/v1/auth/login/', {'email': self.user.email, 'password': 'Clave12345'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        Visit.objects.create(parcela=self.parcel, visitor_name='Visita Portal', purpose='Control', visit_datetime=timezone.now())

        response = self.client.get('/api/v1/maps/visit-summary/?window=all')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['parcela_id'], self.parcel.id)
        self.assertEqual(response.data[0]['visits_count'], 1)

    def test_visit_summary_includes_access_records(self):
        login = self.client.post('/api/v1/auth/login/', {'email': self.user.email, 'password': 'Clave12345'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        AccessRecord.objects.create(
            parcela=self.parcel,
            full_name='Guardia Portal',
            motive='Ingreso visita portal',
            access_datetime=timezone.now(),
        )

        response = self.client.get('/api/v1/maps/visit-summary/?window=all')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['parcela_id'], self.parcel.id)
        self.assertEqual(response.data[0]['visits_count'], 1)
        self.assertEqual(response.data[0]['access_records_count'], 1)
