from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.operations.models import OperationMaintenanceTemplate, OperationOrigin, OperationTask
from apps.operations.services.transitions import create_history


FREQUENCY_DELTAS = {
    'DAILY': lambda count: timedelta(days=count),
    'WEEKLY': lambda count: timedelta(weeks=count),
    'MONTHLY': lambda count: timedelta(days=30 * count),
    'QUARTERLY': lambda count: timedelta(days=91 * count),
    'YEARLY': lambda count: timedelta(days=365 * count),
}


class Command(BaseCommand):
    help = 'Genera tareas operacionales desde plantillas de mantenimiento vencidas.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Muestra cuantas tareas se generarian sin escribir cambios.')
        parser.add_argument('--limit', type=int, default=100, help='Maximo de plantillas a procesar.')

    def handle(self, *args, **options):
        now = timezone.now()
        templates = (
            OperationMaintenanceTemplate.objects.select_related('task_type', 'area', 'geo_asset', 'parcela', 'default_executor')
            .filter(is_active=True, is_deleted=False, next_run_at__lte=now)
            .order_by('next_run_at')[: options['limit']]
        )
        dry_run = options['dry_run']
        created = 0

        for template in templates:
            if dry_run:
                self.stdout.write(f'[dry-run] {template.name}')
                created += 1
                continue

            with transaction.atomic():
                due_at = now + timedelta(days=template.default_due_days)
                task = OperationTask.objects.create(
                    title=template.name,
                    description=template.description,
                    task_type=template.task_type,
                    area=template.area,
                    priority=template.priority,
                    origin=OperationOrigin.MAINTENANCE_TEMPLATE,
                    due_at=due_at,
                    geo_asset=template.geo_asset,
                    parcela=template.parcela or (template.geo_asset.parcela if template.geo_asset_id and template.geo_asset else None),
                    sector=template.sector,
                    executor=template.default_executor,
                    status='ASSIGNED' if template.default_executor_id else 'DETECTED',
                    created_by=template.created_by,
                    updated_by=template.updated_by,
                )
                create_history(task, user=template.updated_by, action='maintenance_generated', new_status=task.status)
                delta_factory = FREQUENCY_DELTAS.get(template.frequency, FREQUENCY_DELTAS['MONTHLY'])
                template.last_generated_at = now
                template.next_run_at = now + delta_factory(template.interval_count)
                template.save(update_fields=['last_generated_at', 'next_run_at', 'updated_at'])
                created += 1

        self.stdout.write(self.style.SUCCESS(f'Tareas generadas: {created}'))
