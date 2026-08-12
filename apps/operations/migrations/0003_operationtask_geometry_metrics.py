from django.db import migrations, models

from apps.geo_operations.services.geometry import validate_geojson_geometry


def populate_geometry_metrics(apps, schema_editor):
    OperationTask = apps.get_model('operations', 'OperationTask')
    fields = [
        'geometry_type',
        'bbox',
        'min_lng',
        'min_lat',
        'max_lng',
        'max_lat',
        'center_lng',
        'center_lat',
        'length_m',
        'perimeter_m',
        'area_m2',
        'vertex_count',
    ]
    for task in OperationTask.objects.exclude(geometry__isnull=True).iterator():
        try:
            summary = validate_geojson_geometry(task.geometry, allowed_geometry_type='ANY')
        except Exception:
            continue
        task.geometry_type = summary.geometry_type
        task.bbox = list(summary.bbox)
        task.min_lng, task.min_lat, task.max_lng, task.max_lat = summary.bbox
        task.center_lng, task.center_lat = summary.center
        task.length_m = summary.length_m
        task.perimeter_m = summary.perimeter_m
        task.area_m2 = summary.area_m2
        task.vertex_count = summary.vertex_count
        task.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0002_seed_initial_catalogs'),
    ]

    operations = [
        migrations.AddField(
            model_name='operationtask',
            name='length_m',
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name='operationtask',
            name='perimeter_m',
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name='operationtask',
            name='area_m2',
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name='operationtask',
            name='vertex_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(populate_geometry_metrics, migrations.RunPython.noop),
    ]
