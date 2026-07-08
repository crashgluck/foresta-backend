from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.data_imports.models import ImportJob


ROLLBACK_MODEL_LABELS = [
    'people.ParcelResident',
    'people.ParcelOwnership',
    'vehicles.Vehicle',
    'finance.CommonExpenseDebt',
    'finance.ServiceDebt',
    'finance.PaymentAgreement',
    'finance.UnpaidFine',
    'utilities.ServiceCut',
    'utilities.ServiceHistory',
    'notes.AdministrativeNote',
    'works.ParcelWorkStatus',
    'people.Person',
    'parcels.Parcel',
]


@dataclass
class RollbackTarget:
    label: str
    model: type
    queryset: object
    count: int
    user_count: int
    null_user_count: int


class Command(BaseCommand):
    help = 'Simula o ejecuta rollback logico de registros creados durante un ImportJob.'

    def add_arguments(self, parser):
        parser.add_argument('job_id', help='UUID del ImportJob que se quiere revertir.')
        parser.add_argument('--execute', action='store_true', help='Ejecuta el rollback. Sin esto solo muestra simulacion.')
        parser.add_argument('--confirm', default='', help='Debe ser igual al job_id para ejecutar.')
        parser.add_argument('--grace-minutes', type=int, default=2, help='Margen alrededor de started_at/finished_at.')
        parser.add_argument(
            '--only-created-by-job-user',
            action='store_true',
            help='Limita a registros cuyo created_by sea el usuario del job. Usar solo si el dry-run muestra trazabilidad.',
        )

    def handle(self, *args, **options):
        job = self._get_job(options['job_id'])
        grace = timedelta(minutes=max(int(options['grace_minutes']), 0))
        started_at = job.started_at - grace
        finished_at = (job.finished_at or timezone.now()) + grace
        only_job_user = bool(options['only_created_by_job_user'])

        if only_job_user and not job.initiated_by_id:
            raise CommandError('El job no tiene initiated_by; no se puede usar --only-created-by-job-user.')

        targets = self._collect_targets(job, started_at, finished_at, only_job_user)
        total = sum(target.count for target in targets)

        self.stdout.write(f'Job: {job.id}')
        self.stdout.write(f'Archivo: {job.source_file}')
        self.stdout.write(f'Estado: {job.status}')
        self.stdout.write(f'Ventana rollback: {started_at.isoformat()} -> {finished_at.isoformat()}')
        self.stdout.write(f'Filtro por usuario del job: {"si" if only_job_user else "no"}')
        self.stdout.write('')

        for target in targets:
            self.stdout.write(
                f'{target.label}: {target.count} candidatos '
                f'(created_by_job_user={target.user_count}, created_by_null={target.null_user_count})'
            )
            for sample in target.queryset.order_by('created_at')[:5]:
                self.stdout.write(f'  - id={sample.pk} created_at={sample.created_at} {sample}')

        self.stdout.write('')
        self.stdout.write(f'Total candidatos: {total}')

        if not options['execute']:
            self.stdout.write(self.style.WARNING('Simulacion solamente. No se modifico la base de datos.'))
            self.stdout.write(f'Para ejecutar: python manage.py rollback_import_job {job.id} --execute --confirm {job.id}')
            return

        if options['confirm'] != str(job.id):
            raise CommandError('Para ejecutar debes pasar --confirm con el UUID exacto del job.')

        with transaction.atomic():
            deleted_at = timezone.now()
            for target in targets:
                updated = target.queryset.update(is_deleted=True, deleted_at=deleted_at)
                self.stdout.write(self.style.SUCCESS(f'{target.label}: rollback logico aplicado a {updated} registros.'))

        self.stdout.write(self.style.SUCCESS(f'Rollback finalizado. Registros marcados como eliminados: {total}'))

    def _get_job(self, job_id: str) -> ImportJob:
        try:
            return ImportJob.objects.get(id=job_id)
        except ImportJob.DoesNotExist as exc:
            raise CommandError(f'No existe ImportJob {job_id}') from exc

    def _collect_targets(self, job: ImportJob, started_at, finished_at, only_job_user: bool) -> list[RollbackTarget]:
        targets = []
        for label in ROLLBACK_MODEL_LABELS:
            model = apps.get_model(label)
            manager = getattr(model, 'all_objects', model.objects)
            queryset = manager.filter(is_deleted=False, created_at__gte=started_at, created_at__lte=finished_at)
            user_queryset = queryset.filter(created_by_id=job.initiated_by_id) if job.initiated_by_id else queryset.none()
            if only_job_user:
                queryset = user_queryset
            count = queryset.count()
            if count == 0:
                continue
            targets.append(
                RollbackTarget(
                    label=label,
                    model=model,
                    queryset=queryset,
                    count=count,
                    user_count=user_queryset.count(),
                    null_user_count=queryset.filter(created_by_id__isnull=True).count(),
                )
            )
        return targets
