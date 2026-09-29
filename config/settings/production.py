from .base import *

DEBUG = False

SERVE_API_DOCS = env_bool('SERVE_API_DOCS', False)
SERVE_MEDIA_FILES = env_bool('SERVE_MEDIA_FILES', True)

SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True)
SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', True)
CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', True)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Defaults livianos para cPanel/Passenger en planes basicos.
SESSION_ENGINE = os.getenv('SESSION_ENGINE', 'django.contrib.sessions.backends.signed_cookies')
SESSION_COOKIE_AGE = env_int('SESSION_COOKIE_AGE', 60 * 60 * 8, minimum=300)

AUDIT_LOG_READS = env_bool('AUDIT_LOG_READS', False)
AUDIT_LOG_PAYLOAD = env_bool('AUDIT_LOG_PAYLOAD', False)
AUDIT_MAX_PAYLOAD_BYTES = env_int('AUDIT_MAX_PAYLOAD_BYTES', 2000, minimum=0, maximum=12000)
SESSION_AUDIT_LOG_REFRESH = env_bool('SESSION_AUDIT_LOG_REFRESH', False)
CURRENT_USER_AUTHENTICATE_SAFE_METHODS = env_bool('CURRENT_USER_AUTHENTICATE_SAFE_METHODS', False)

DASHBOARD_CACHE_SECONDS = env_int('DASHBOARD_CACHE_SECONDS', 60, minimum=0)
DASHBOARD_MAX_RANGE_DAYS = env_int('DASHBOARD_MAX_RANGE_DAYS', 120, minimum=7, maximum=730)
FINANCE_SUMMARY_CACHE_SECONDS = env_int('FINANCE_SUMMARY_CACHE_SECONDS', 45, minimum=0)
FINANCE_CONSOLIDATED_CACHE_SECONDS = env_int('FINANCE_CONSOLIDATED_CACHE_SECONDS', 45, minimum=0, maximum=300)
MAPS_OWNERS_CACHE_SECONDS = env_int('MAPS_OWNERS_CACHE_SECONDS', 120, minimum=0)
MAPS_OPTIONS_CACHE_SECONDS = env_int('MAPS_OPTIONS_CACHE_SECONDS', 120, minimum=0)
MAPS_VISIT_SUMMARY_CACHE_SECONDS = env_int('MAPS_VISIT_SUMMARY_CACHE_SECONDS', 45, minimum=0)
GEO_CHOICES_CACHE_SECONDS = env_int('GEO_CHOICES_CACHE_SECONDS', 900, minimum=0, maximum=3600)
GEO_MAP_CACHE_SECONDS = env_int('GEO_MAP_CACHE_SECONDS', 75, minimum=0, maximum=300)
GEO_MONTHLY_REPORT_CACHE_SECONDS = env_int('GEO_MONTHLY_REPORT_CACHE_SECONDS', 180, minimum=0, maximum=600)
OPERATION_CHOICES_CACHE_SECONDS = env_int('OPERATION_CHOICES_CACHE_SECONDS', 900, minimum=0, maximum=3600)
OPERATION_MAP_CACHE_SECONDS = env_int('OPERATION_MAP_CACHE_SECONDS', 60, minimum=0, maximum=300)
OPERATION_SUMMARY_CACHE_SECONDS = env_int('OPERATION_SUMMARY_CACHE_SECONDS', 60, minimum=0, maximum=300)
MISSION_SUMMARY_CACHE_SECONDS = env_int('MISSION_SUMMARY_CACHE_SECONDS', 90, minimum=0, maximum=300)

LOGGING['root']['level'] = os.getenv('LOG_LEVEL', 'WARNING')

TEMPLATES[0]['APP_DIRS'] = False
TEMPLATES[0]['OPTIONS']['loaders'] = [
    (
        'django.template.loaders.cached.Loader',
        [
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        ],
    )
]
