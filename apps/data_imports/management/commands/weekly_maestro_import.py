import hashlib
import json
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from apps.accounts.models import User
from apps.data_imports.models import ImportJob, ImportStatus
from apps.data_imports.services.excel_importer import ExcelMasterImporter


PROFILE_SHEETS = {
    'weekly': [
        'Mora GC',
        'DESUDAS AyS',
        'MORA CONVENIO',
        'Cortes Vigentes',
        'ANOTACIONES',
        'HISTORICO AYS',
    ],
    'owners': ['Datos_Propietarios', 'OTROS DUEÑOS', 'RESIDENTES', 'PPU_LOGOS'],
    'finance': ['Mora GC', 'DESUDAS AyS', 'MORA CONVENIO', 'Multas-Convenios impagas'],
    'services': ['Cortes Vigentes', 'HISTORICO AYS', 'ANOTACIONES'],
    'works': ['OBRAS'],
    'full': list(ExcelMasterImporter.SHEET_REQUIREMENTS.keys()),
}

ACTIVE_STATUSES = [ImportStatus.PENDING, ImportStatus.RUNNING]


class Command(BaseCommand):
    help = 'Orquesta cargas semanales del maestro Excel con preflight, preview, backup y reporte.'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, help='Ruta del archivo Excel maestro.')
        parser.add_argument(
            '--mode',
            choices=['preview', 'commit', 'auto'],
            default='preview',
            help='preview: solo dry-run; commit: import real; auto: preview y commit si pasa umbrales.',
        )
        parser.add_argument(
            '--profile',
            choices=sorted(PROFILE_SHEETS.keys()),
            default='weekly',
            help='Grupo de hojas recomendado. Usa --sheets para sobrescribir.',
        )
        parser.add_argument('--sheets', default='', help='Lista separada por coma de hojas a procesar.')
        parser.add_argument('--user-email', default='', help='Email del usuario responsable de la carga.')
        parser.add_argument('--max-errors', type=int, default=0, help='Errores maximos permitidos para considerar aprobado el preview.')
        parser.add_argument('--max-warnings', type=int, default=None, help='Advertencias maximas permitidas. Por defecto no limita.')
        parser.add_argument('--report-dir', default='', help='Directorio para guardar el reporte JSON.')
        parser.add_argument('--skip-backup', action='store_true', help='No crear backup local antes del commit.')
        parser.add_argument('--allow-running', action='store_true', help='Permite ejecutar aunque existan importaciones activas.')
        parser.add_argument('--empty-row-break-limit', type=int, default=0, help='Corte de filas vacias consecutivas para el parser.')

    def handle(self, *args, **options):
        file_path = Path(options['file']).expanduser().resolve()
        if not file_path.exists():
            raise CommandError(f'Archivo no encontrado: {file_path}')

        sheets = self._selected_sheets(options['profile'], options['sheets'])
        user = self._get_user(options['user_email'])
        report = self._base_report(file_path, options, sheets)

        if not options['allow_running']:
            self._assert_no_active_imports()

        self.stdout.write(self.style.NOTICE('1/4 Preflight del Excel'))
        structure = self._inspect_structure(file_path, sheets, options['empty_row_break_limit'])
        report['structure'] = structure
        try:
            self._validate_selected_structure(structure, sheets)
        except CommandError as exc:
            report['gate_errors'] = [str(exc)]
            report_path = self._write_report(report, options['report_dir'])
            self.stdout.write(self.style.WARNING(f'Reporte guardado: {report_path}'))
            raise
        self.stdout.write(self.style.SUCCESS(f'Hojas OK: {", ".join(structure["processable_sheets"])}'))

        preview_job = None
        commit_job = None
        backup_path = ''

        if options['mode'] in {'preview', 'auto'}:
            self.stdout.write(self.style.NOTICE('2/4 Preview sin persistir datos'))
            preview_job = self._run_import(
                file_path=file_path,
                dry_run=True,
                user=user,
                sheets=sheets,
                empty_row_break_limit=options['empty_row_break_limit'],
            )
            report['preview_job'] = self._serialize_job(preview_job)
            self._write_job_line('Preview', preview_job)
            self._assert_job_within_thresholds_or_report(preview_job, options, report)

        if options['mode'] in {'commit', 'auto'}:
            self.stdout.write(self.style.NOTICE('3/4 Respaldo previo'))
            if options['skip_backup']:
                report['backup'] = {'skipped': True, 'reason': '--skip-backup'}
                self.stdout.write(self.style.WARNING('Backup omitido por --skip-backup.'))
            else:
                backup_path = self._backup_database(file_path)
                report['backup'] = {'skipped': False, 'path': backup_path}
                if backup_path:
                    self.stdout.write(self.style.SUCCESS(f'Backup creado: {backup_path}'))
                else:
                    self.stdout.write(self.style.WARNING('No se creo backup local. Verifica snapshot externo de la base.'))

            self.stdout.write(self.style.NOTICE('4/4 Importacion real'))
            commit_job = self._run_import(
                file_path=file_path,
                dry_run=False,
                user=user,
                sheets=sheets,
                empty_row_break_limit=options['empty_row_break_limit'],
            )
            report['commit_job'] = self._serialize_job(commit_job)
            self._write_job_line('Commit', commit_job)

        report_path = self._write_report(report, options['report_dir'])
        self.stdout.write(self.style.SUCCESS(f'Reporte guardado: {report_path}'))

        final_job = commit_job or preview_job
        if final_job:
            self._assert_job_within_thresholds(final_job, options['max_errors'], options['max_warnings'])

    def _selected_sheets(self, profile: str, raw_sheets: str) -> list[str]:
        if raw_sheets:
            sheets = [item.strip() for item in raw_sheets.split(',') if item.strip()]
            if not sheets:
                raise CommandError('--sheets no contiene hojas validas.')
            return sheets
        return list(PROFILE_SHEETS[profile])

    def _get_user(self, email: str):
        if not email:
            return None
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise CommandError(f'No existe usuario con email {email}')
        return user

    def _base_report(self, file_path: Path, options: dict, sheets: list[str]) -> dict:
        return {
            'generated_at': timezone.now().isoformat(),
            'source_file': file_path.name,
            'source_path': str(file_path),
            'source_hash': self._hash_file(file_path),
            'mode': options['mode'],
            'profile': options['profile'],
            'selected_sheets': sheets,
            'thresholds': {
                'max_errors': options['max_errors'],
                'max_warnings': options['max_warnings'],
            },
            'structure': {},
            'preview_job': None,
            'commit_job': None,
            'backup': {},
        }

    def _assert_no_active_imports(self):
        active_jobs = list(ImportJob.objects.filter(status__in=ACTIVE_STATUSES).order_by('-started_at')[:5])
        if not active_jobs:
            return
        active_ids = ', '.join(f'{job.id} ({job.status})' for job in active_jobs)
        raise CommandError(f'Hay importaciones activas: {active_ids}. Usa --allow-running solo si estas seguro.')

    def _inspect_structure(self, file_path: Path, sheets: list[str], empty_row_break_limit: int) -> dict:
        importer = ExcelMasterImporter(
            file_path=str(file_path),
            dry_run=True,
            sheets=sheets,
            empty_row_break_limit=empty_row_break_limit or None,
        )
        return importer.inspect_structure()

    def _validate_selected_structure(self, structure: dict, sheets: list[str]):
        if structure.get('selected_unknown_sheets'):
            raise CommandError(f'Hojas no soportadas: {", ".join(structure["selected_unknown_sheets"])}')

        checks_by_name = {check['sheet_name']: check for check in structure.get('checks', [])}
        invalid = []
        for sheet in sheets:
            check = checks_by_name.get(sheet)
            if not check:
                invalid.append(f'{sheet}: sin validacion')
                continue
            if not check.get('exists'):
                invalid.append(f'{sheet}: hoja no encontrada')
            elif not check.get('header_found'):
                invalid.append(f'{sheet}: encabezado no detectado')
            elif check.get('missing_keywords'):
                invalid.append(f'{sheet}: faltan columnas {", ".join(check["missing_keywords"])}')

        if invalid:
            raise CommandError('Preflight fallido: ' + ' | '.join(invalid))

    def _run_import(self, *, file_path: Path, dry_run: bool, user, sheets: list[str], empty_row_break_limit: int) -> ImportJob:
        importer = ExcelMasterImporter(
            file_path=str(file_path),
            dry_run=dry_run,
            initiated_by=user,
            sheets=sheets,
            empty_row_break_limit=empty_row_break_limit or None,
        )
        return importer.run()

    def _backup_database(self, source_file: Path) -> str:
        if connection.vendor != 'sqlite':
            return ''

        db_name = settings.DATABASES['default'].get('NAME')
        db_path = Path(db_name)
        if not db_path.exists():
            return ''

        timestamp = timezone.localtime().strftime('%Y%m%d_%H%M%S')
        backup_dir = Path(settings.BASE_DIR) / 'backups' / 'imports'
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f'{timestamp}_{source_file.stem[:80]}_{db_path.name}'

        with connection.cursor() as cursor:
            cursor.execute('PRAGMA wal_checkpoint(FULL)')

        shutil.copy2(db_path, backup_path)
        for suffix in ('-wal', '-shm'):
            sidecar = Path(f'{db_path}{suffix}')
            if sidecar.exists():
                shutil.copy2(sidecar, backup_dir / f'{backup_path.name}{suffix}')
        return str(backup_path)

    def _serialize_job(self, job: ImportJob) -> dict:
        details = job.details or {}
        return {
            'id': str(job.id),
            'status': job.status,
            'dry_run': job.dry_run,
            'source_file': job.source_file,
            'source_hash': job.source_hash,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'finished_at': job.finished_at.isoformat() if job.finished_at else None,
            'totals': {
                'inserted': job.total_inserted,
                'updated': job.total_updated,
                'skipped': job.total_skipped,
                'errors': job.total_errors,
                'warnings': job.total_warnings,
            },
            'summary': details.get('summary', {}),
            'sheet_results': list(
                job.sheet_results.order_by('sheet_name').values(
                    'sheet_name',
                    'status',
                    'rows_read',
                    'inserted',
                    'updated',
                    'skipped',
                    'errors',
                    'warnings',
                    'summary',
                )
            ),
            'issues_sample': list(
                job.issues.order_by('-severity', 'sheet_name', 'row_number', 'created_at').values(
                    'severity',
                    'sheet_name',
                    'row_number',
                    'column_name',
                    'error_code',
                    'message',
                    'raw_value',
                )[:100]
            ),
        }

    def _write_job_line(self, label: str, job: ImportJob):
        self.stdout.write(
            f'{label} job {job.id}: status={job.status}, inserted={job.total_inserted}, '
            f'updated={job.total_updated}, skipped={job.total_skipped}, errors={job.total_errors}, warnings={job.total_warnings}'
        )

    def _assert_job_within_thresholds(self, job: ImportJob, max_errors: int, max_warnings: int | None):
        errors = self._job_threshold_errors(job, max_errors, max_warnings)
        if errors:
            raise CommandError(' | '.join(errors))

    def _assert_job_within_thresholds_or_report(self, job: ImportJob, options: dict, report: dict):
        errors = self._job_threshold_errors(job, options['max_errors'], options['max_warnings'])
        if not errors:
            return
        report['gate_errors'] = errors
        report_path = self._write_report(report, options['report_dir'])
        self.stdout.write(self.style.WARNING(f'Reporte guardado: {report_path}'))
        raise CommandError(' | '.join(errors))

    def _job_threshold_errors(self, job: ImportJob, max_errors: int, max_warnings: int | None) -> list[str]:
        errors = []
        if job.total_errors > max_errors:
            errors.append(f'Job {job.id} supera max-errors: {job.total_errors} > {max_errors}')
        if max_warnings is not None and job.total_warnings > max_warnings:
            errors.append(f'Job {job.id} supera max-warnings: {job.total_warnings} > {max_warnings}')
        return errors

    def _write_report(self, report: dict, report_dir: str) -> str:
        timestamp = timezone.localtime().strftime('%Y%m%d_%H%M%S')
        target_dir = Path(report_dir).expanduser().resolve() if report_dir else Path(settings.BASE_DIR) / 'reports' / 'imports'
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '_' for ch in report['source_file'][:80])
        path = target_dir / f'{timestamp}_{report["mode"]}_{safe_name}.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        return str(path)

    def _hash_file(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open('rb') as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()
