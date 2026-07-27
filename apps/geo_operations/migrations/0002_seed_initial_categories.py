from django.db import migrations

from apps.geo_operations.constants import INITIAL_GEO_CATEGORIES


def seed_categories(apps, schema_editor):
    GeoAssetCategory = apps.get_model('geo_operations', 'GeoAssetCategory')
    for row in INITIAL_GEO_CATEGORIES:
        GeoAssetCategory.objects.update_or_create(
            slug=row['slug'],
            defaults={
                'name': row['name'],
                'description': row['description'],
                'geometry_type': row['geometry_type'],
                'color': row['color'],
                'icon': row['icon'],
                'sort_order': row['sort_order'],
                'is_active': True,
                'extra_schema': {},
                'is_deleted': False,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('geo_operations', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]
