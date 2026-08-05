from django.db import migrations

from apps.operations.constants import (
    INITIAL_OPERATION_AREAS,
    INITIAL_OPERATION_BLOCK_REASONS,
    INITIAL_OPERATION_TASK_TYPES,
)


def seed_catalogs(apps, schema_editor):
    OperationArea = apps.get_model('operations', 'OperationArea')
    OperationTaskType = apps.get_model('operations', 'OperationTaskType')
    OperationBlockReason = apps.get_model('operations', 'OperationBlockReason')

    for row in INITIAL_OPERATION_AREAS:
        OperationArea.objects.update_or_create(
            slug=row['slug'],
            defaults={
                'name': row['name'],
                'description': row.get('description', ''),
                'is_active': True,
                'sort_order': row['sort_order'],
                'is_deleted': False,
            },
        )

    for row in INITIAL_OPERATION_TASK_TYPES:
        OperationTaskType.objects.update_or_create(
            slug=row['slug'],
            defaults={
                'name': row['name'],
                'description': row.get('description', ''),
                'is_active': True,
                'sort_order': row['sort_order'],
                'is_deleted': False,
            },
        )

    for row in INITIAL_OPERATION_BLOCK_REASONS:
        OperationBlockReason.objects.update_or_create(
            slug=row['slug'],
            defaults={
                'name': row['name'],
                'description': row.get('description', ''),
                'is_active': True,
                'sort_order': row['sort_order'],
                'is_deleted': False,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_catalogs, migrations.RunPython.noop),
    ]
