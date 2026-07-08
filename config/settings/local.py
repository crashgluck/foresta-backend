from .base import *  # noqa

DEBUG = True

# En desarrollo local trabajamos siempre con SQLite para evitar tocar MySQL/cPanel por accidente.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'CONN_MAX_AGE': 0,
        'OPTIONS': {
            'timeout': SQLITE_TIMEOUT_SECONDS,
        },
    }
}
