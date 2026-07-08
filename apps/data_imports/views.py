import csv
import hashlib
import json
from pathlib import Path
import uuid

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.renderers import BaseRenderer
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.models import UserRole
from apps.core.permissions import RoleBasedActionPermission
from apps.data_imports.models import ImportIssue, ImportJob, ImportRowResult, ImportStatus, ImportUploadSession, ImportUploadStatus
from apps.data_imports.serializers import ImportIssueSerializer, ImportJobSerializer, ImportRowResultSerializer, ImportUploadSessionSerializer
from apps.data_imports.services.excel_importer import ExcelMasterImporter


SUPPORTED_EXCEL_EXTENSIONS = ('.xlsx', '.xlsm', '.xltx', '.xltm')


class CSVRenderer(BaseRenderer):
    media_type = 'text/csv'
    format = 'csv'
    charset = 'utf-8'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


def _parse_sheets(raw_value):
    if not raw_value:
        return None
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    if isinstance(raw_value, str):
        return [item.strip() for item in raw_value.split(',') if item.strip()]
    return None


def _parse_column_mapping(raw_value):
    if not raw_value:
        return {}
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            payload = json.loads(raw_value)
            if not isinstance(payload, dict):
                raise ValueError('column_mapping debe ser un objeto JSON.')
            return payload
        except json.JSONDecodeError:
            raise ValueError('column_mapping tiene un JSON inválido.')
    raise ValueError('column_mapping debe enviarse como JSON objeto.')


def _parse_bool(raw_value, default=False):
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, (int, float)):
        return bool(raw_value)
    if isinstance(raw_value, str):
        value = raw_value.strip().lower()
        if value in {'1', 'true', 'yes', 'si', 'on'}:
            return True
        if value in {'0', 'false', 'no', 'off'}:
            return False
    return default


def _file_sha256(upload_file) -> str:
    digest = hashlib.sha256()
    current_position = upload_file.tell()
    upload_file.seek(0)
    for chunk in upload_file.chunks():
        digest.update(chunk)
    upload_file.seek(current_position)
    return digest.hexdigest()


def _path_sha256(file_path: str) -> str:
    digest = hashlib.sha256()
    with Path(file_path).open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _create_pending_import_job(
    *,
    file_path: str,
    dry_run: bool,
    initiated_by,
    sheets: list[str] | None,
    column_mapping: dict,
    source_file: str | None = None,
    source_hash: str = '',
    upload_session_id: str = '',
) -> ImportJob:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f'Archivo no encontrado: {file_path}')

    details = {
        'execution_mode': 'queued',
        'selected_sheets': sheets or [],
        'column_mapping': column_mapping or {},
    }
    if upload_session_id:
        details['upload_session_id'] = upload_session_id

    return ImportJob.objects.create(
        source_file=source_file or path.name,
        source_hash=source_hash or _path_sha256(file_path),
        source_path=str(path),
        dry_run=dry_run,
        status=ImportStatus.PENDING,
        initiated_by=initiated_by,
        details=details,
    )


def _validate_upload(upload):
    if not upload:
        return 'Debes adjuntar un archivo Excel en el campo "file".'
    if not upload.name.lower().endswith(SUPPORTED_EXCEL_EXTENSIONS):
        return 'Formato no soportado. Usa un archivo .xlsx/.xlsm. Los .xls antiguos deben convertirse antes de importar.'
    if getattr(upload, 'size', 0) <= 0:
        return 'El archivo esta vacio o no pudo leerse.'
    return ''


def _job_response_payload(job: ImportJob, issues_key='issues', row_results_key='row_results', limit=400):
    issues = job.issues.order_by('-severity', 'sheet_name', 'row_number', '-created_at')[:limit]
    row_results = job.row_results.order_by('sheet_name', 'row_number', 'created_at')[:limit]
    return {
        'job': ImportJobSerializer(job).data,
        issues_key: ImportIssueSerializer(issues, many=True).data,
        row_results_key: ImportRowResultSerializer(row_results, many=True).data,
    }


class ImportJobViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ImportJob.objects.all().prefetch_related('sheet_results')
    serializer_class = ImportJobSerializer
    permission_classes = [RoleBasedActionPermission]
    filterset_fields = ['status', 'dry_run', 'initiated_by']
    ordering_fields = ['started_at', 'finished_at', 'status']
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    required_roles_per_action = {
        'list': UserRole.OPERADOR,
        'retrieve': UserRole.OPERADOR,
        'run': UserRole.OPERADOR,
        'preview_upload': UserRole.OPERADOR,
        'run_upload': UserRole.OPERADOR,
        'issues_report': UserRole.OPERADOR,
        'cancel': UserRole.OPERADOR,
        'stop': UserRole.OPERADOR,
        'terminate': UserRole.OPERADOR,
        'cancel_requested': UserRole.OPERADOR,
    }

    @action(detail=False, methods=['post'])
    def run(self, request):
        file_path = request.data.get('file_path')
        if not file_path:
            return Response({'detail': 'file_path es requerido'}, status=status.HTTP_400_BAD_REQUEST)

        sheets = _parse_sheets(request.data.get('sheets'))
        dry_run = _parse_bool(request.data.get('dry_run', False), default=False)
        try:
            column_mapping = _parse_column_mapping(request.data.get('column_mapping'))
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        queue = _parse_bool(request.data.get('queue'), default=getattr(settings, 'IMPORT_QUEUE_BY_DEFAULT', True) and not dry_run)
        if queue:
            try:
                job = _create_pending_import_job(
                    file_path=file_path,
                    dry_run=dry_run,
                    initiated_by=request.user,
                    sheets=sheets,
                    column_mapping=column_mapping,
                )
            except FileNotFoundError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return Response(ImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)

        importer = ExcelMasterImporter(
            file_path=file_path,
            dry_run=dry_run,
            initiated_by=request.user,
            sheets=sheets,
            column_mapping=column_mapping,
        )
        job = importer.run()
        return Response(ImportJobSerializer(job).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='preview-upload')
    def preview_upload(self, request):
        upload = request.FILES.get('file')
        upload_error = _validate_upload(upload)
        if upload_error:
            return Response({'detail': upload_error}, status=status.HTTP_400_BAD_REQUEST)

        sheets = _parse_sheets(request.data.get('sheets'))
        try:
            column_mapping = _parse_column_mapping(request.data.get('column_mapping'))
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        source_hash = _file_sha256(upload)
        skip_preview = _parse_bool(request.data.get('skip_preview'), default=False)

        session = ImportUploadSession.objects.create(
            original_filename=upload.name,
            uploaded_by=request.user,
            source_hash=source_hash,
            selected_sheets=sheets or [],
            column_mapping=column_mapping,
            status=ImportUploadStatus.UPLOADED,
        )
        session.stored_file.save(f'{uuid.uuid4()}_{upload.name}', upload, save=True)

        if skip_preview:
            return Response(
                {
                    'upload_session': ImportUploadSessionSerializer(session).data,
                    'structure': {},
                    'preview_job': None,
                    'preview_issues': [],
                    'preview_row_results': [],
                    'skipped_preview': True,
                },
                status=status.HTTP_201_CREATED,
            )

        importer = ExcelMasterImporter(
            file_path=session.stored_file.path,
            dry_run=True,
            initiated_by=request.user,
            sheets=sheets,
            column_mapping=column_mapping,
        )
        try:
            structure = importer.inspect_structure()
        except Exception:
            structure = {}
        preview_job = importer.run()
        structure = structure or (preview_job.details or {}).get('structure', {})

        session.preview_job = preview_job
        session.status = ImportUploadStatus.PREVIEWED
        session.save(update_fields=['preview_job', 'status', 'last_used_at'])

        preview_payload = _job_response_payload(preview_job, issues_key='preview_issues', row_results_key='preview_row_results')
        return Response(
            {
                'upload_session': ImportUploadSessionSerializer(session).data,
                'structure': structure,
                'preview_job': preview_payload['job'],
                'preview_issues': preview_payload['preview_issues'],
                'preview_row_results': preview_payload['preview_row_results'],
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['post'], url_path='run-upload')
    def run_upload(self, request):
        upload_session_id = request.data.get('upload_session_id')
        if not upload_session_id:
            return Response({'detail': 'upload_session_id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        session = ImportUploadSession.objects.filter(id=upload_session_id).first()
        if not session:
            return Response({'detail': 'Sesión de carga no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        if not session.stored_file:
            return Response({'detail': 'La sesión no tiene archivo asociado.'}, status=status.HTTP_400_BAD_REQUEST)

        sheets = _parse_sheets(request.data.get('sheets')) or session.selected_sheets or None
        try:
            request_mapping = _parse_column_mapping(request.data.get('column_mapping'))
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        column_mapping = request_mapping or session.column_mapping or {}

        queue = _parse_bool(request.data.get('queue'), default=getattr(settings, 'IMPORT_QUEUE_BY_DEFAULT', True))
        if queue:
            try:
                job = _create_pending_import_job(
                    file_path=session.stored_file.path,
                    dry_run=False,
                    initiated_by=request.user,
                    sheets=sheets,
                    column_mapping=column_mapping,
                    source_file=session.original_filename,
                    source_hash=session.source_hash,
                    upload_session_id=str(session.id),
                )
            except FileNotFoundError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            session.executed_job = job
            session.status = ImportUploadStatus.EXECUTED
            session.selected_sheets = sheets or []
            session.column_mapping = column_mapping
            session.save(update_fields=['executed_job', 'status', 'selected_sheets', 'column_mapping', 'last_used_at'])

            job_payload = _job_response_payload(job)
            return Response({'upload_session': ImportUploadSessionSerializer(session).data, **job_payload}, status=status.HTTP_202_ACCEPTED)

        importer = ExcelMasterImporter(
            file_path=session.stored_file.path,
            dry_run=False,
            initiated_by=request.user,
            sheets=sheets,
            column_mapping=column_mapping,
        )
        job = importer.run()

        session.executed_job = job
        session.status = ImportUploadStatus.EXECUTED
        session.selected_sheets = sheets or []
        session.column_mapping = column_mapping
        session.save(update_fields=['executed_job', 'status', 'selected_sheets', 'column_mapping', 'last_used_at'])

        job_payload = _job_response_payload(job)
        return Response({'upload_session': ImportUploadSessionSerializer(session).data, **job_payload}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='issues-report', renderer_classes=[CSVRenderer])
    def issues_report(self, request, pk=None):
        job = self.get_object()
        issues = job.issues.order_by('sheet_name', 'row_number', 'created_at')
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="import_issues_{job.id}.csv"'
        writer = csv.writer(response)
        writer.writerow(['severity', 'sheet_name', 'row_number', 'column_name', 'error_code', 'message', 'raw_value', 'created_at'])
        for issue in issues:
            writer.writerow(
                [
                    issue.severity,
                    issue.sheet_name,
                    issue.row_number or '',
                    issue.column_name or '',
                    issue.error_code or '',
                    issue.message or '',
                    issue.raw_value or '',
                    timezone.localtime(issue.created_at).isoformat(),
                ]
            )
        return response

    def _request_cancel(self, request, job: ImportJob, source: str):
        terminal_statuses = {
            ImportStatus.SUCCESS,
            ImportStatus.PARTIAL,
            ImportStatus.FAILED,
            ImportStatus.CANCELLED,
        }
        if job.status in terminal_statuses:
            return Response(
                {
                    'detail': f'El job ya está finalizado con estado {job.status}.',
                    'status': job.status,
                    'id': str(job.id),
                },
                status=status.HTTP_409_CONFLICT,
            )

        details = dict(job.details or {})
        details['cancel_requested'] = True
        details['cancel_requested_at'] = timezone.now().isoformat()
        details['cancel_requested_by'] = str(getattr(request.user, 'id', ''))
        details['cancel_request_source'] = source

        job.status = ImportStatus.CANCELLED
        job.finished_at = timezone.now()
        job.details = details
        job.save(update_fields=['status', 'finished_at', 'details'])

        return Response(
            {
                'detail': 'Solicitud de cancelación registrada.',
                'status': job.status,
                'id': str(job.id),
                'cancel_requested': True,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        job = self.get_object()
        return self._request_cancel(request, job, source='cancel')

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        job = self.get_object()
        return self._request_cancel(request, job, source='stop')

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        job = self.get_object()
        return self._request_cancel(request, job, source='terminate')

    @action(detail=True, methods=['post'], url_path='cancel_requested')
    def cancel_requested(self, request, pk=None):
        job = self.get_object()
        return self._request_cancel(request, job, source='cancel_requested')


class ImportIssueViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ImportIssue.objects.select_related('import_job', 'sheet_result').all()
    serializer_class = ImportIssueSerializer
    permission_classes = [RoleBasedActionPermission]
    filterset_fields = ['severity', 'sheet_name', 'import_job']
    ordering_fields = ['created_at', 'row_number']

    required_roles_per_action = {
        'list': UserRole.OPERADOR,
        'retrieve': UserRole.OPERADOR,
    }


class ImportRowResultViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ImportRowResult.objects.select_related('import_job', 'sheet_result').all()
    serializer_class = ImportRowResultSerializer
    permission_classes = [RoleBasedActionPermission]
    filterset_fields = ['action', 'sheet_name', 'import_job']
    ordering_fields = ['created_at', 'row_number']

    required_roles_per_action = {
        'list': UserRole.OPERADOR,
        'retrieve': UserRole.OPERADOR,
    }
