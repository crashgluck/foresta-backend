from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole
from apps.parcels.models import Parcel


@override_settings(API_LIST_CACHE_SECONDS=60, API_CACHE_MAX_PAYLOAD_BYTES=100_000)
class CachedReadMixinTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='operador-cache',
            email='operador-cache@example.com',
            password='testpass123',
            role=UserRole.OPERADOR,
        )
        self.client.force_authenticate(self.user)
        Parcel.objects.create(codigo_parcela='A-1')

    def _result_codes(self, response):
        payload = response.data
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        return {row['codigo_parcela'] for row in rows}

    def test_list_cache_hits_and_invalidates_after_write(self):
        first = self.client.get('/api/v1/parcelas/', {'page_size': 10})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first['X-Foresta-Cache'], 'MISS')

        second = self.client.get('/api/v1/parcelas/', {'page_size': 10})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second['X-Foresta-Cache'], 'HIT')

        created = self.client.post('/api/v1/parcelas/', {'codigo_parcela': 'C-5'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)

        after_write = self.client.get('/api/v1/parcelas/', {'page_size': 10})
        self.assertEqual(after_write.status_code, 200)
        self.assertEqual(after_write['X-Foresta-Cache'], 'MISS')
        self.assertIn('C-5', self._result_codes(after_write))
