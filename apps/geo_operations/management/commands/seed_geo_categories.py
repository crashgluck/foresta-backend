from django.core.management.base import BaseCommand

from apps.geo_operations.constants import INITIAL_GEO_CATEGORIES
from apps.geo_operations.models import GeoAssetCategory


class Command(BaseCommand):
    help = 'Carga o actualiza categorias iniciales de infraestructura georreferenciada.'

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for row in INITIAL_GEO_CATEGORIES:
            _, was_created = GeoAssetCategory.objects.update_or_create(
                slug=row['slug'],
                defaults={
                    'name': row['name'],
                    'description': row['description'],
                    'geometry_type': row['geometry_type'],
                    'color': row['color'],
                    'icon': row['icon'],
                    'sort_order': row['sort_order'],
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f'Categorias georreferenciadas listas: created={created}, updated={updated}'))
