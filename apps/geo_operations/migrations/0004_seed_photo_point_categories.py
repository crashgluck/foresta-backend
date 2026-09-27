from django.db import migrations


PHOTO_POINT_CATEGORIES = [
    {
        'name': 'Letreros viales',
        'slug': 'letreros-viales',
        'description': 'Letreros, senaletica vial y puntos fotograficos asociados.',
        'service_type': 'ROADS',
        'geometry_type': 'POINT',
        'color': '#2563eb',
        'icon': 'signpost',
        'sort_order': 186,
    },
    {
        'name': 'Empalizados',
        'slug': 'empalizados',
        'description': 'Empalizados, cierres rusticos y puntos fotograficos asociados.',
        'service_type': 'SECURITY',
        'geometry_type': 'POINT',
        'color': '#92400e',
        'icon': 'fence',
        'sort_order': 187,
    },
    {
        'name': 'Luminaria postes',
        'slug': 'luminaria-postes',
        'description': 'Luminarias montadas en postes y puntos fotograficos asociados.',
        'service_type': 'ELECTRIC',
        'geometry_type': 'POINT',
        'color': '#eab308',
        'icon': 'lightbulb',
        'sort_order': 188,
    },
    {
        'name': 'Luminaria camino',
        'slug': 'luminaria-camino',
        'description': 'Luminarias asociadas a caminos y puntos fotograficos asociados.',
        'service_type': 'ELECTRIC',
        'geometry_type': 'POINT',
        'color': '#f59e0b',
        'icon': 'lightbulb',
        'sort_order': 189,
    },
    {
        'name': 'Instalaciones',
        'slug': 'instalaciones',
        'description': 'Instalaciones puntuales levantadas con registro fotografico.',
        'service_type': 'GENERAL',
        'geometry_type': 'POINT',
        'color': '#334155',
        'icon': 'landmark',
        'sort_order': 190,
    },
]


def seed_photo_point_categories(apps, schema_editor):
    GeoAssetCategory = apps.get_model('geo_operations', 'GeoAssetCategory')
    for row in PHOTO_POINT_CATEGORIES:
        defaults = {key: value for key, value in row.items() if key != 'slug'}
        GeoAssetCategory.objects.update_or_create(
            slug=row['slug'],
            defaults={
                **defaults,
                'is_active': True,
                'extra_schema': {},
                'is_deleted': False,
            },
        )
    GeoAssetCategory.objects.filter(slug='instalaciones-generales').update(sort_order=240)


class Migration(migrations.Migration):
    dependencies = [
        ('geo_operations', '0003_geoasset_photo_geoasset_photo_content_type_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_photo_point_categories, migrations.RunPython.noop),
    ]
