# Optimizacion para cPanel basico

## Variables recomendadas

Usa `.env.example` como base y ajusta credenciales reales. Para hosting compartido conviene:

- `DJANGO_ENV=production`
- `DJANGO_DEBUG=false`
- `DB_ENGINE=mysql`
- `LOG_LEVEL=WARNING`
- `API_PAGE_SIZE=20`
- `API_MAX_PAGE_SIZE=50`
- `AUDIT_LOG_READS=false`
- `AUDIT_LOG_PAYLOAD=false`
- `SESSION_AUDIT_LOG_REFRESH=false`
- `DASHBOARD_CACHE_SECONDS=60`
- `MAPS_OWNERS_CACHE_SECONDS=120`
- `MAPS_OPTIONS_CACHE_SECONDS=120`
- `MAPS_VISIT_SUMMARY_CACHE_SECONDS=45`
- `FINANCE_SUMMARY_CACHE_SECONDS=45`

## cPanel / Passenger

El archivo `passenger_wsgi.py` deja listo el entrypoint para Passenger:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

En cPanel apunta la app Python al directorio `foresta-backend/`. No uses `runserver` en produccion.

## Para reducir CPU e I/O

- Sirve `/static/` directamente desde Apache/cPanel cuando sea posible.
- No subas sourcemaps (`*.map`) del frontend al servidor si no necesitas depurar produccion.
- Evita ejecutar importaciones Excel grandes en horas de uso; hazlas manualmente y de a una.
- Mantén Swagger/Redoc apagado con `SERVE_API_DOCS=false`.
- Si necesitas auditoria completa por unos minutos, activa `AUDIT_LOG_READS=true`, revisa lo necesario y vuelve a `false`.

