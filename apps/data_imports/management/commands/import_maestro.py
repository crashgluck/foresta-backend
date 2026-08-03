from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.data_imports.services.excel_importer import ExcelMasterImporter, EXCEL_IMPORT_PROFILE_SHEETS


class Command(BaseCommand):
    help = 'Importa archivo maestro Excel al sistema.'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, help='Ruta del archivo Excel')
        parser.add_argument('--dry-run', action='store_true', help='Simula importación sin persistir datos')
        parser.add_argument(
            '--profile',
            choices=sorted([*EXCEL_IMPORT_PROFILE_SHEETS.keys(), 'full']),
            default='',
            help='Perfil de hojas a importar. Usa --sheets para sobrescribir.',
        )
        parser.add_argument('--sheets', default='', help='Lista separada por coma de hojas a importar')
        parser.add_argument('--user-email', default='', help='Email del usuario que ejecuta')

    def handle(self, *args, **options):
        user = None
        if options['user_email']:
            user = User.objects.filter(email__iexact=options['user_email']).first()

        sheets = [s.strip() for s in options['sheets'].split(',') if s.strip()] if options['sheets'] else None
        importer = ExcelMasterImporter(
            file_path=options['file'],
            dry_run=options['dry_run'],
            initiated_by=user,
            sheets=sheets,
            profile=options['profile'],
        )
        job = importer.run()

        self.stdout.write(self.style.SUCCESS(f'Import job {job.id} finalizado con estado {job.status}'))
        self.stdout.write(
            f"inserted={job.total_inserted}, updated={job.total_updated}, skipped={job.total_skipped}, errors={job.total_errors}, warnings={job.total_warnings}"
        )

