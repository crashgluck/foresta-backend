from datetime import datetime
from tempfile import TemporaryDirectory

from django.contrib import admin as django_admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole
from apps.geo_operations.models import GeoAsset, GeoAssetCategory
from apps.operations.admin import OperationTaskAdmin
from apps.operations.models import (
    OperationArea,
    OperationBlockReason,
    OperationExecutor,
    OperationExecutorKind,
    OperationReportExport,
    OperationTask,
    OperationTaskHistory,
    OperationTaskStatus,
    OperationTaskType,
)
from apps.parcels.models import Parcel


class OperationTaskAdminConfigTests(SimpleTestCase):
    def test_detected_at_filter_does_not_use_date_hierarchy(self):
        self.assertIsNone(OperationTaskAdmin.date_hierarchy)
        self.assertIn(('detected_at', django_admin.DateFieldListFilter), OperationTaskAdmin.list_filter)


class OperationsApiTests(APITestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username='operations-operator',
            email='operations-operator@example.com',
            password='testpass123',
            role=UserRole.OPERADOR,
        )
        self.reader = User.objects.create_user(
            username='operations-reader',
            email='operations-reader@example.com',
            password='testpass123',
            role=UserRole.CONSULTA,
        )
        self.admin = User.objects.create_user(
            username='operations-admin',
            email='operations-admin@example.com',
            password='testpass123',
            role=UserRole.ADMINISTRADOR,
        )
        self.area = OperationArea.objects.create(name='Seguridad test', slug='seguridad-tests', sort_order=1)
        self.task_type = OperationTaskType.objects.create(name='Hallazgo test', slug='hallazgo-tests', sort_order=1)
        self.block_reason = OperationBlockReason.objects.create(name='Proveedor test', slug='proveedor-tests', sort_order=1)
        self.executor = OperationExecutor.objects.create(
            kind=OperationExecutorKind.INTERNAL_WORKER,
            name='Trabajador sin cuenta',
            contact='radio 1',
        )
        self.parcel = Parcel.objects.create(codigo_parcela='N-19')
        self.asset_category = GeoAssetCategory.objects.create(
            name='Grifos operaciones test',
            slug='grifos-operaciones-test',
            service_type='SECURITY',
            geometry_type='POINT',
            color='#ef4444',
        )
        self.asset_geometry = {'type': 'Point', 'coordinates': [-70.66, -33.45]}
        self.asset = GeoAsset.objects.create(
            title='Grifo norte',
            category=self.asset_category,
            geometry_type='POINT',
            geometry=self.asset_geometry,
            parcela=self.parcel,
        )

    def _auth_operator(self):
        self.client.force_authenticate(self.operator)

    def _create_task(self, **overrides):
        defaults = {
            'title': 'Revision operacional',
            'task_type': self.task_type,
            'area': self.area,
            'priority': 'MEDIUM',
            'registered_by': self.operator,
            'geo_asset': self.asset,
            'parcela': self.parcel,
        }
        defaults.update(overrides)
        return OperationTask.objects.create(**defaults)

    def _results(self, response):
        return response.data.get('results', response.data)

    def _aware(self, year, month, day):
        return timezone.make_aware(datetime(year, month, day, 10, 0, 0))

    def test_create_task_linked_to_geo_asset_without_duplicating_geometry(self):
        self._auth_operator()
        response = self.client.post(
            '/api/v1/operations/tasks/',
            {
                'title': 'Filtracion en grifo',
                'task_type': self.task_type.id,
                'area': self.area.id,
                'priority': 'HIGH',
                'geo_asset': self.asset.id,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        task = OperationTask.objects.get(pk=response.data['id'])
        self.assertIsNone(task.geometry)
        self.assertEqual(task.geo_asset_id, self.asset.id)
        self.assertEqual(task.parcela_id, self.parcel.id)
        self.assertEqual(task.registered_by_id, self.operator.id)
        self.assertTrue(OperationTaskHistory.objects.filter(task=task, action='created').exists())

    def test_create_task_with_own_line_geometry_records_metrics(self):
        self._auth_operator()
        geometry = {'type': 'LineString', 'coordinates': [[-70.66, -33.45], [-70.661, -33.451]]}
        response = self.client.post(
            '/api/v1/operations/tasks/',
            {
                'title': 'Limpieza de tramo',
                'task_type': self.task_type.id,
                'area': self.area.id,
                'priority': 'MEDIUM',
                'geometry': geometry,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        task = OperationTask.objects.get(pk=response.data['id'])
        self.assertEqual(task.geometry_type, 'LINE')
        self.assertEqual(task.vertex_count, 2)
        self.assertGreater(task.length_m, 0)

    def test_executor_without_user_is_allowed(self):
        self._auth_operator()
        response = self.client.post(
            '/api/v1/operations/executors/',
            {'kind': OperationExecutorKind.PROVIDER, 'name': 'Proveedor externo'},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(OperationExecutor.objects.get(pk=response.data['id']).user_id)

    def test_reader_cannot_create_task_and_cannot_see_costs(self):
        task = self._create_task(cost_estimated='25000.00', cost_real='12000.00')
        self.client.force_authenticate(self.reader)

        forbidden = self.client.post(
            '/api/v1/operations/tasks/',
            {'title': 'Sin permiso', 'task_type': self.task_type.id, 'area': self.area.id},
            format='json',
        )
        self.assertEqual(forbidden.status_code, 403)

        detail = self.client.get(f'/api/v1/operations/tasks/{task.id}/')
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertNotIn('cost_estimated', detail.data)
        self.assertNotIn('cost_real', detail.data)

    def test_operator_cannot_set_costs(self):
        self._auth_operator()
        response = self.client.post(
            '/api/v1/operations/tasks/',
            {
                'title': 'Costo restringido',
                'task_type': self.task_type.id,
                'area': self.area.id,
                'cost_estimated': '1000.00',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_assigned_transition_requires_executor(self):
        task = self._create_task()
        self._auth_operator()
        response = self.client.post(
            f'/api/v1/operations/tasks/{task.id}/transition/',
            {'new_status': OperationTaskStatus.ASSIGNED},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        task.refresh_from_db()
        self.assertEqual(task.status, OperationTaskStatus.DETECTED)

    def test_status_cannot_be_changed_with_patch(self):
        task = self._create_task()
        self._auth_operator()
        response = self.client.patch(
            f'/api/v1/operations/tasks/{task.id}/',
            {'status': OperationTaskStatus.CANCELLED},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        task.refresh_from_db()
        self.assertEqual(task.status, OperationTaskStatus.DETECTED)

    def test_executed_cannot_close_without_verification(self):
        task = self._create_task()
        self._auth_operator()

        assign = self.client.post(f'/api/v1/operations/tasks/{task.id}/assign/', {'executor': self.executor.id}, format='json')
        self.assertEqual(assign.status_code, 200, assign.data)
        progress = self.client.post(
            f'/api/v1/operations/tasks/{task.id}/transition/',
            {'new_status': OperationTaskStatus.IN_PROGRESS},
            format='json',
        )
        self.assertEqual(progress.status_code, 200, progress.data)
        executed = self.client.post(
            f'/api/v1/operations/tasks/{task.id}/transition/',
            {'new_status': OperationTaskStatus.EXECUTED, 'obtained_result': 'Reparacion realizada'},
            format='json',
        )
        self.assertEqual(executed.status_code, 200, executed.data)

        close_without_verification = self.client.post(f'/api/v1/operations/tasks/{task.id}/close/', {}, format='json')
        self.assertEqual(close_without_verification.status_code, 400)

        verified = self.client.post(f'/api/v1/operations/tasks/{task.id}/verify/', {'comment': 'Validado en terreno'}, format='json')
        self.assertEqual(verified.status_code, 200, verified.data)
        closed = self.client.post(f'/api/v1/operations/tasks/{task.id}/close/', {'comment': 'Cierre normal'}, format='json')
        self.assertEqual(closed.status_code, 200, closed.data)
        task.refresh_from_db()
        self.assertEqual(task.status, OperationTaskStatus.CLOSED)
        self.assertEqual(task.verified_by_id, self.operator.id)
        self.assertIsNotNone(task.closed_at)

    def test_admin_force_close_from_executed_is_audited(self):
        task = self._create_task(status=OperationTaskStatus.ASSIGNED, executor=self.executor)
        task.status = OperationTaskStatus.IN_PROGRESS
        task.save()
        task.obtained_result = 'Trabajo terminado con validacion excepcional'
        task.status = OperationTaskStatus.EXECUTED
        task.save()

        self.client.force_authenticate(self.admin)
        response = self.client.post(
            f'/api/v1/operations/tasks/{task.id}/close/',
            {'force': True, 'comment': 'Cierre forzado autorizado'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        task.refresh_from_db()
        self.assertEqual(task.status, OperationTaskStatus.CLOSED)
        self.assertEqual(task.verified_by_id, self.admin.id)
        history = task.history.filter(action='transition', new_status=OperationTaskStatus.CLOSED).first()
        self.assertIsNotNone(history)
        self.assertTrue(history.changed_fields['force'])

    def test_block_creates_active_block_and_history(self):
        task = self._create_task()
        self._auth_operator()
        response = self.client.post(
            f'/api/v1/operations/tasks/{task.id}/block/',
            {'reason': self.block_reason.id, 'description': 'Esperando proveedor'},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        task.refresh_from_db()
        self.assertEqual(task.status, OperationTaskStatus.BLOCKED)
        self.assertTrue(task.blocks.filter(is_active=True, reason=self.block_reason).exists())
        self.assertTrue(task.history.filter(action='transition', new_status=OperationTaskStatus.BLOCKED).exists())

    def test_month_filter_uses_detected_updated_or_closed_period(self):
        july_detected = self._create_task(title='Detectada julio', detected_at=self._aware(2026, 7, 5))
        july_closed = self._create_task(
            title='Cerrada julio',
            detected_at=self._aware(2026, 6, 20),
            status=OperationTaskStatus.CLOSED,
            verification_at=self._aware(2026, 7, 7),
            closed_at=self._aware(2026, 7, 8),
        )
        self._create_task(title='Agosto', detected_at=self._aware(2026, 8, 3))

        self.client.force_authenticate(self.reader)
        response = self.client.get('/api/v1/operations/tasks/', {'month': '2026-07', 'page_size': 50})
        self.assertEqual(response.status_code, 200, response.data)
        ids = {row['id'] for row in self._results(response)}
        self.assertIn(july_detected.id, ids)
        self.assertIn(july_closed.id, ids)
        self.assertNotIn(OperationTask.objects.get(title='Agosto').id, ids)

    def test_geojson_uses_asset_geometry_when_task_has_no_geometry(self):
        task = self._create_task(title='Mapa sin geometria propia')
        self.client.force_authenticate(self.reader)
        response = self.client.get('/api/v1/operations/tasks/geojson/', {'page_size': 50})
        self.assertEqual(response.status_code, 200, response.data)
        feature = next(item for item in response.data['features'] if item['id'] == task.id)
        self.assertEqual(feature['geometry'], self.asset_geometry)
        self.assertEqual(feature['properties']['geometry_source'], 'geo_asset')

    def test_map_bbox_filters_task_or_asset_geometry(self):
        inside = self._create_task(title='Dentro del bbox')
        outside_category = GeoAssetCategory.objects.create(
            name='Fuera operaciones test',
            slug='fuera-operaciones-test',
            service_type='SECURITY',
            geometry_type='POINT',
            color='#2563eb',
        )
        outside_asset = GeoAsset.objects.create(
            title='Activo fuera',
            category=outside_category,
            geometry_type='POINT',
            geometry={'type': 'Point', 'coordinates': [-71.5, -34.2]},
        )
        outside = self._create_task(title='Fuera del bbox', geo_asset=outside_asset, parcela=None)

        self.client.force_authenticate(self.reader)
        response = self.client.get('/api/v1/operations/tasks/map/', {'bbox': '-70.7,-33.5,-70.6,-33.4', 'page_size': 50})
        self.assertEqual(response.status_code, 200, response.data)
        ids = {row['id'] for row in response.data}
        self.assertIn(inside.id, ids)
        self.assertNotIn(outside.id, ids)

    def test_summary_and_pdf_use_selected_filters(self):
        high = self._create_task(title='Alta prioridad', priority='HIGH')
        self._create_task(title='Baja prioridad', priority='LOW')
        self.client.force_authenticate(self.reader)

        summary = self.client.get('/api/v1/operations/tasks/summary/', {'priority': 'HIGH'})
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data['summary']['total_tasks'], 1)
        self.assertNotIn('cost_estimated', summary.data['summary'])
        self.assertNotIn('cost_real', summary.data['summary'])

        pdf = self.client.get('/api/v1/operations/tasks/report-pdf/', {'priority': 'HIGH'})
        self.assertEqual(pdf.status_code, 200)
        self.assertIn('application/pdf', pdf['Content-Type'])
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        export = OperationReportExport.objects.latest('created_at')
        self.assertEqual(export.filters['priority'], 'HIGH')
        self.assertEqual(export.total_tasks, 1)
        self.assertTrue(OperationTask.objects.filter(pk=high.pk).exists())

    def test_evidence_upload_records_file_and_history(self):
        task = self._create_task()
        self._auth_operator()
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            upload = SimpleUploadedFile('acta.pdf', b'%PDF-1.4 evidence', content_type='application/pdf')
            response = self.client.post(
                f'/api/v1/operations/tasks/{task.id}/evidences/',
                {'evidence_type': 'DOCUMENT', 'file': upload, 'comment': 'Acta de trabajo'},
                format='multipart',
            )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['original_name'], 'acta.pdf')
        self.assertTrue(task.history.filter(action='evidence').exists())
