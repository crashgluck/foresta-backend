from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole
from apps.geo_operations.models import GeoAsset, GeoAssetCategory


class GeoOperationsApiTests(APITestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username='geo-operator',
            email='geo-operator@example.com',
            password='testpass123',
            role=UserRole.OPERADOR,
        )
        self.reader = User.objects.create_user(
            username='geo-reader',
            email='geo-reader@example.com',
            password='testpass123',
            role=UserRole.CONSULTA,
        )
        self.admin = User.objects.create_user(
            username='geo-admin',
            email='geo-admin@example.com',
            password='testpass123',
            role=UserRole.ADMINISTRADOR,
        )
        self.point_category = GeoAssetCategory.objects.create(
            name='Grifos test',
            slug='grifos-test',
            geometry_type='POINT',
            color='#ef4444',
        )
        self.line_category = GeoAssetCategory.objects.create(
            name='Lineas test',
            slug='lineas-test',
            geometry_type='LINE',
            color='#eab308',
        )
        self.polygon_category = GeoAssetCategory.objects.create(
            name='Zonas test',
            slug='zonas-test',
            geometry_type='POLYGON',
            color='#f97316',
        )

    def _auth_operator(self):
        self.client.force_authenticate(self.operator)

    def _create_asset(self, category, geometry, **overrides):
        payload = {
            'title': overrides.pop('title', 'Activo geo'),
            'category': category.id,
            'geometry': geometry,
            'operational_status': overrides.pop('operational_status', 'ACTIVE'),
            'criticality': overrides.pop('criticality', 'MEDIUM'),
            **overrides,
        }
        response = self.client.post('/api/v1/geo/assets/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def test_create_point_asset(self):
        self._auth_operator()
        response = self._create_asset(
            self.point_category,
            {'type': 'Point', 'coordinates': [-70.66, -33.45]},
        )
        self.assertEqual(response.data['geometry_type'], 'POINT')
        self.assertEqual(response.data['vertex_count'], 1)
        self.assertEqual(response.data['bbox'], [-70.66, -33.45, -70.66, -33.45])

    def test_create_line_asset(self):
        self._auth_operator()
        response = self._create_asset(
            self.line_category,
            {'type': 'LineString', 'coordinates': [[-70.66, -33.45], [-70.65, -33.44]]},
        )
        self.assertEqual(response.data['geometry_type'], 'LINE')
        self.assertGreater(response.data['length_m'], 0)

    def test_create_polygon_asset(self):
        self._auth_operator()
        response = self._create_asset(
            self.polygon_category,
            {
                'type': 'Polygon',
                'coordinates': [[[-70.66, -33.45], [-70.65, -33.45], [-70.65, -33.44], [-70.66, -33.45]]],
            },
        )
        self.assertEqual(response.data['geometry_type'], 'POLYGON')
        self.assertGreater(response.data['area_m2'], 0)

    def test_reject_invalid_geojson(self):
        self._auth_operator()
        response = self.client.post(
            '/api/v1/geo/assets/',
            {
                'title': 'Invalido',
                'category': self.point_category.id,
                'geometry': {'type': 'Point', 'coordinates': [-200, -33.45]},
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('geometry', response.data['errors'])

    def test_reject_geometry_not_allowed_by_category(self):
        self._auth_operator()
        response = self.client.post(
            '/api/v1/geo/assets/',
            {
                'title': 'Linea en categoria punto',
                'category': self.point_category.id,
                'geometry': {'type': 'LineString', 'coordinates': [[-70.66, -33.45], [-70.65, -33.44]]},
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('geometry', response.data['errors'])

    def test_reader_cannot_create_asset(self):
        self.client.force_authenticate(self.reader)
        response = self.client.post(
            '/api/v1/geo/assets/',
            {
                'title': 'Sin permiso',
                'category': self.point_category.id,
                'geometry': {'type': 'Point', 'coordinates': [-70.66, -33.45]},
            },
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_bbox_filter_returns_visible_assets(self):
        self._auth_operator()
        inside = self._create_asset(
            self.point_category,
            {'type': 'Point', 'coordinates': [-70.66, -33.45]},
            title='Dentro',
        )
        self._create_asset(
            self.point_category,
            {'type': 'Point', 'coordinates': [-71.66, -34.45]},
            title='Fuera',
        )

        response = self.client.get('/api/v1/geo/assets/map/', {'bbox': '-70.7,-33.5,-70.6,-33.4'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data], [inside.data['id']])

    def test_export_kml_and_kmz(self):
        self._auth_operator()
        self._create_asset(self.point_category, {'type': 'Point', 'coordinates': [-70.66, -33.45]}, title='Grifo norte')

        kml_response = self.client.get('/api/v1/geo/assets/export/', {'file_format': 'kml'})
        self.assertEqual(kml_response.status_code, 200)
        self.assertIn('application/vnd.google-earth.kml+xml', kml_response['Content-Type'])
        self.assertIn(b'Grifo norte', kml_response.content)

        kmz_response = self.client.get('/api/v1/geo/assets/export/', {'file_format': 'kmz'})
        self.assertEqual(kmz_response.status_code, 200)
        self.assertIn('application/vnd.google-earth.kmz', kmz_response['Content-Type'])
        self.assertTrue(kmz_response.content.startswith(b'PK'))

    def test_destroy_is_logical(self):
        self._auth_operator()
        created = self._create_asset(self.point_category, {'type': 'Point', 'coordinates': [-70.66, -33.45]})
        asset_id = created.data['id']

        self.client.force_authenticate(self.admin)
        response = self.client.delete(f'/api/v1/geo/assets/{asset_id}/')
        self.assertEqual(response.status_code, 204)

        asset = GeoAsset.all_objects.get(pk=asset_id)
        self.assertTrue(asset.is_deleted)
        self.assertFalse(asset.is_active)
