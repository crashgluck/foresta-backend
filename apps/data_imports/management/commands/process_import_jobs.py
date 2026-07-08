import time

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.core.thread_local import set_current_user
from apps.data_imports.models import ImportJob, ImportStatus
from apps.data_imports.services.excel_importer import ExcelMasterImporter


class Command(BaseCommand):
    help = 'Procesa importaciones encoladas en estado PENDING. Pensado para cron/cPanel.'

    def add_arguments(self, parser):
        parser.add_argument('--max-jobs', type=int, default=1, help='Cantidad maxima de jobs a procesar en esta ejecucion.')
        parser.add_argument('--max-seconds', type=int, default=45, help='Tiempo maximo aproximado de ejecucion.')

    def handle(self, *args, **options):
        self._prepare_database_connection()
        max_jobs = max(int(options['max_jobs']), 1)
        max_seconds = max(int(options['max_seconds']), 5)
        deadline = time.monotonic() + max_seconds
        processed = 0

        while processed < max_jobs and time.monotonic() < deadline:
            job = self._claim_next_job()
            if not job:
                break

            self.stdout.write(f'Procesando import job {job.id} ({job.source_file})')
            try:
                details = job.details or {}
                selected_sheets = details.get('selected_sheets') or None
                column_mapping = details.get('column_mapping') or {}
                importer = ExcelMasterImporter(
                    file_path=job.source_path,
                    dry_run=job.dry_run,
                    initiated_by=job.initiated_by,
                    sheets=selected_sheets,
                    column_mapping=column_mapping,
                )
                set_current_user(job.initiated_by)
                try:
                    result = importer.run(job=job)
                finally:
                    set_current_user(None)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Import job {result.id} finalizado: status={result.status}, '
                        f'inserted={result.total_inserted}, updated={result.total_updated}, '
                        f'skipped={result.total_skipped}, errors={result.total_errors}'
                    )
                )
            except Exception as exc:  # pragma: no cover
                self._mark_failed(job, exc)
                self.stderr.write(self.style.ERROR(f'Import job {job.id} fallo: {exc}'))

            processed += 1

        self.stdout.write(f'Jobs procesados: {processed}')

    def _prepare_database_connection(self):
        if connection.vendor != 'sqlite':
            return
        timeout_seconds = getattr(settings, 'SQLITE_TIMEOUT_SECONDS', 30)
        with connection.cursor() as cursor:
            cursor.execute(f'PRAGMA busy_timeout = {int(timeout_seconds) * 1000}')
            cursor.execute('PRAGMA journal_mode = WAL')

    def _claim_next_job(self):
        with transaction.atomic():
            job = (
                ImportJob.objects.select_for_update()
                .filter(status=ImportStatus.PENDING)
                .order_by('started_at')
                .first()
            )
            if not job:
                return None

            details = dict(job.details or {})
            details['claimed_at'] = timezone.now().isoformat()
            job.status = ImportStatus.RUNNING
            job.details = details
            job.save(update_fields=['status', 'details'])
            return job

    def _mark_failed(self, job: ImportJob, exc: Exception):
        details = dict(job.details or {})
        details.setdefault('fatal_errors', []).append(
            {
                'code': 'worker_crash',
                'message': str(exc),
            }
        )
        job.status = ImportStatus.FAILED
        job.finished_at = timezone.now()
        job.total_errors = max(job.total_errors, 1)
        job.details = details
        job.save(update_fields=['status', 'finished_at', 'total_errors', 'details'])
