import hashlib
import logging
import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
env_path = BASE_DIR / '.env'
load_dotenv(env_path if env_path.exists() else BASE_DIR / '.env.real')
logger = logging.getLogger(__name__)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw_value = os.getenv(name)
    try:
        value = int(raw_value) if raw_value is not None else default
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def env_list(name: str, default: str = '') -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-only-change-this-key-to-a-secure-value-1234567890')
DEBUG = env_bool('DJANGO_DEBUG', False)
ALLOWED_HOSTS = [
    'api-foresta.aguasyservicioslaz.cl',
    'localhost',
    '127.0.0.1',
]
SERVE_API_DOCS = env_bool('SERVE_API_DOCS', DEBUG)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'django_filters',
    'apps.core.apps.CoreConfig',
    'apps.accounts',
    'apps.parcels',
    'apps.people',
    'apps.vehicles',
    'apps.finance',
    'apps.utilities',
    'apps.notes',
    'apps.works',
    'apps.access_control',
    'apps.maps_app',
    'apps.acquisitions',
    'apps.missions',
    'apps.supervisor',
    'apps.data_imports',
    'apps.audits',
    'apps.api',
    'apps.iot',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.middleware.CurrentUserMiddleware',
    'apps.audits.middleware.AuditTrailMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DB_ENGINE = os.getenv('DB_ENGINE', 'mysql').strip().lower()
DB_CONN_MAX_AGE = env_int('DB_CONN_MAX_AGE', 0, minimum=0)
DB_CONN_HEALTH_CHECKS = env_bool('DB_CONN_HEALTH_CHECKS', False)
SQLITE_TIMEOUT_SECONDS = env_int('SQLITE_TIMEOUT_SECONDS', 30, minimum=5, maximum=120)

if DB_ENGINE == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', ''),
            'USER': os.getenv('DB_USER', ''),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'CONN_MAX_AGE': DB_CONN_MAX_AGE,
            'CONN_HEALTH_CHECKS': DB_CONN_HEALTH_CHECKS,
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                'charset': 'utf8mb4',
            },
        }
    }
elif DB_ENGINE == 'sqlite':
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
else:
    raise ValueError(f"DB_ENGINE no soportado: {DB_ENGINE}")

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-cl'
TIME_ZONE = os.getenv('TIME_ZONE', 'America/Santiago')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': os.getenv('CACHE_LOCATION', 'foresta-api'),
        'TIMEOUT': env_int('CACHE_DEFAULT_TIMEOUT', 300, minimum=1),
        'OPTIONS': {
            'MAX_ENTRIES': env_int('CACHE_MAX_ENTRIES', 1000, minimum=100),
            'CULL_FREQUENCY': env_int('CACHE_CULL_FREQUENCY', 3, minimum=1),
        },
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000')
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000')

NODOTECH_API_BASE_URL = os.getenv('NODOTECH_API_BASE_URL', 'https://nodotech.aguasyservicioslaz.cl/api/v1').rstrip('/')
NODOTECH_EMAIL = os.getenv('NODOTECH_EMAIL', '')
NODOTECH_PASSWORD = os.getenv('NODOTECH_PASSWORD', '')
NODOTECH_REQUEST_TIMEOUT = int(os.getenv('NODOTECH_REQUEST_TIMEOUT', os.getenv('NODOTECH_TIMEOUT_SECONDS', '10')))
NODOTECH_TIMEOUT_SECONDS = NODOTECH_REQUEST_TIMEOUT
NODOTECH_DEFAULT_PULSE_MS = int(os.getenv('NODOTECH_DEFAULT_PULSE_MS', '700'))
NODOTECH_ACCESS_TOKEN_CACHE_SECONDS = int(os.getenv('NODOTECH_ACCESS_TOKEN_CACHE_SECONDS', '840'))
NODOTECH_REFRESH_TOKEN_CACHE_SECONDS = int(os.getenv('NODOTECH_REFRESH_TOKEN_CACHE_SECONDS', '604800'))

API_PAGE_SIZE = env_int('API_PAGE_SIZE', 25, minimum=5, maximum=100)
API_MAX_PAGE_SIZE = env_int('API_MAX_PAGE_SIZE', 50, minimum=API_PAGE_SIZE, maximum=200)

IMPORT_EMPTY_ROW_BREAK_LIMIT = env_int('IMPORT_EMPTY_ROW_BREAK_LIMIT', 150, minimum=25, maximum=2000)
IMPORT_LOG_SUCCESS_ROWS = env_bool('IMPORT_LOG_SUCCESS_ROWS', False)
IMPORT_QUEUE_BY_DEFAULT = env_bool('IMPORT_QUEUE_BY_DEFAULT', True)

DASHBOARD_CACHE_SECONDS = env_int('DASHBOARD_CACHE_SECONDS', 0, minimum=0)
DASHBOARD_MAX_RANGE_DAYS = env_int('DASHBOARD_MAX_RANGE_DAYS', 365, minimum=7, maximum=730)
FINANCE_SUMMARY_CACHE_SECONDS = env_int('FINANCE_SUMMARY_CACHE_SECONDS', 0, minimum=0)
MAPS_OWNERS_CACHE_SECONDS = env_int('MAPS_OWNERS_CACHE_SECONDS', 30, minimum=0)
MAPS_OPTIONS_CACHE_SECONDS = env_int('MAPS_OPTIONS_CACHE_SECONDS', 0, minimum=0)
MAPS_VISIT_SUMMARY_CACHE_SECONDS = env_int('MAPS_VISIT_SUMMARY_CACHE_SECONDS', 0, minimum=0)

AUDIT_TRAIL_ENABLED = env_bool('AUDIT_TRAIL_ENABLED', True)
AUDIT_LOG_READS = env_bool('AUDIT_LOG_READS', False)
AUDIT_LOG_PAYLOAD = env_bool('AUDIT_LOG_PAYLOAD', True)
AUDIT_LOG_QUERY_PARAMS = env_bool('AUDIT_LOG_QUERY_PARAMS', True)
AUDIT_MAX_PAYLOAD_BYTES = env_int('AUDIT_MAX_PAYLOAD_BYTES', 12000, minimum=0, maximum=12000)
AUDIT_EXCLUDED_PREFIXES = tuple(env_list('AUDIT_EXCLUDED_PREFIXES'))
SESSION_AUDIT_ENABLED = env_bool('SESSION_AUDIT_ENABLED', True)
SESSION_AUDIT_LOG_REFRESH = env_bool('SESSION_AUDIT_LOG_REFRESH', True)
CURRENT_USER_AUTHENTICATE_SAFE_METHODS = env_bool('CURRENT_USER_AUTHENTICATE_SAFE_METHODS', False)

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'apps.core.pagination.StandardResultsSetPagination',
    'PAGE_SIZE': API_PAGE_SIZE,
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
}

raw_jwt_signing_key = os.getenv('JWT_SIGNING_KEY', SECRET_KEY)
if len(raw_jwt_signing_key.encode('utf-8')) < 32:
    logger.warning(
        'JWT signing key shorter than 32 bytes. Deriving SHA-256 key. Set JWT_SIGNING_KEY>=32 bytes to remove this warning.'
    )
    JWT_SIGNING_KEY = hashlib.sha256(raw_jwt_signing_key.encode('utf-8')).hexdigest()
else:
    JWT_SIGNING_KEY = raw_jwt_signing_key

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv('JWT_ACCESS_MINUTES', '15'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv('JWT_REFRESH_DAYS', '7'))),
    'ROTATE_REFRESH_TOKENS': env_bool('JWT_ROTATE_REFRESH_TOKENS', False),
    'BLACKLIST_AFTER_ROTATION': env_bool('JWT_BLACKLIST_AFTER_ROTATION', False),
    'UPDATE_LAST_LOGIN': env_bool('JWT_UPDATE_LAST_LOGIN', False),
    'AUTH_HEADER_TYPES': ('Bearer',),
    'SIGNING_KEY': JWT_SIGNING_KEY,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Parcelas API',
    'DESCRIPTION': 'API de gestión de parcelas, propietarios, servicios y finanzas.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('LOG_LEVEL', 'INFO'),
    },
}
