from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole
from apps.parcels.models import Parcel


class ParcelModelTests(TestCase):
    def test_normaliza_codigo_parcela(self):
        parcel = Parcel.objects.create(codigo_parcela=' n  - 0019 ')
        self.assertEqual(parcel.codigo_parcela, 'N-19')
        self.assertEqual(parcel.codigo_parcela_key, 'N-19')
        self.assertEqual(parcel.letra_lote, 'N')
        self.assertEqual(parcel.numero_lote, 19)

    def test_codigo_invalido_lanza_error(self):
        parcel = Parcel(codigo_parcela='INVALIDO')
        with self.assertRaises(ValidationError):
            parcel.full_clean()


class ParcelSearchApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='consulta',
            email='consulta@example.com',
            password='testpass123',
            role=UserRole.CONSULTA,
        )
        self.client.force_authenticate(self.user)
        Parcel.objects.create(codigo_parcela='A-1')
        Parcel.objects.create(codigo_parcela='B-3')

    def _result_codes(self, response):
        self.assertEqual(response.status_code, 200)
        payload = response.data
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        return {row['codigo_parcela'] for row in rows}

    def test_search_accepts_zero_padded_parcel_code(self):
        response = self.client.get('/api/v1/parcelas/', {'search': 'A-01'})
        self.assertIn('A-1', self._result_codes(response))

    def test_search_accepts_compact_parcel_code(self):
        response = self.client.get('/api/v1/parcelas/', {'search': 'B03'})
        self.assertIn('B-3', self._result_codes(response))

    def test_consolidated_by_code_accepts_zero_padded_code(self):
        response = self.client.get('/api/v1/parcelas/by-code/B-03/ficha-consolidada/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['codigo_parcela'], 'B-3')
