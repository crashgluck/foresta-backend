from django.apps import AppConfig
from django.conf import settings
from django.db.backends.signals import connection_created


def configure_sqlite_connection(sender, connection, **kwargs):
    if connection.vendor != 'sqlite':
        return

    timeout_seconds = getattr(settings, 'SQLITE_TIMEOUT_SECONDS', 30)
    with connection.cursor() as cursor:
        cursor.execute(f'PRAGMA busy_timeout = {int(timeout_seconds) * 1000}')
        cursor.execute('PRAGMA journal_mode = WAL')


class CoreConfig(AppConfig):
    name = 'apps.core'

    def ready(self):
        connection_created.connect(configure_sqlite_connection, dispatch_uid='foresta_sqlite_connection_pragmas')
