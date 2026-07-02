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

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-only-change-this-key-to-a-secure-value-1234567890')
DEBUG = os.getenv('DJANGO_DEBUG', 'false').lower() == 'true'
ALLOWED_HOSTS = [h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]

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
    'apps.core',
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

DB_ENGINE = os.getenv('DB_ENGINE', 'sqlite').strip().lower()

# Alias para leer y exportar la base SQLite antigua.
# Localmente apunta a backend/db.sqlite3.
DATABASES = {
    'sqlite_old': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

if DB_ENGINE == 'mysql':
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME', ''),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }

elif DB_ENGINE == 'postgres':
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'parcelas'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }

else:
    # Desarrollo local normal: SQLite sigue siendo la base principal.
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }

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

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

CORS_ALLOWED_ORIGINS = [o.strip() for o in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',') if o.strip()]
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',') if o.strip()]

NODOTECH_API_BASE_URL = os.getenv('NODOTECH_API_BASE_URL', 'https://nodotech.aguasyservicioslaz.cl/api/v1').rstrip('/')
NODOTECH_EMAIL = os.getenv('NODOTECH_EMAIL', '')
NODOTECH_PASSWORD = os.getenv('NODOTECH_PASSWORD', '')
NODOTECH_REQUEST_TIMEOUT = int(os.getenv('NODOTECH_REQUEST_TIMEOUT', os.getenv('NODOTECH_TIMEOUT_SECONDS', '10')))
NODOTECH_TIMEOUT_SECONDS = NODOTECH_REQUEST_TIMEOUT
NODOTECH_DEFAULT_PULSE_MS = int(os.getenv('NODOTECH_DEFAULT_PULSE_MS', '700'))
NODOTECH_ACCESS_TOKEN_CACHE_SECONDS = int(os.getenv('NODOTECH_ACCESS_TOKEN_CACHE_SECONDS', '840'))
NODOTECH_REFRESH_TOKEN_CACHE_SECONDS = int(os.getenv('NODOTECH_REFRESH_TOKEN_CACHE_SECONDS', '604800'))

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
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': int(os.getenv('API_PAGE_SIZE', '25')),
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
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
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
