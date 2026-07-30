# Optimizacion para cPanel basico

## Variables recomendadas

Usa `.env.example` como base y ajusta credenciales reales. Para hosting compartido conviene:

- `DJANGO_ENV=production`
- `DJANGO_DEBUG=false`
- `SERVE_MEDIA_FILES=true`
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
- `IMPORT_QUEUE_BY_DEFAULT=true`
- `IMPORT_LOG_SUCCESS_ROWS=false`
- `IMPORT_EMPTY_ROW_BREAK_LIMIT=150`

## cPanel / Passenger

El archivo `passenger_wsgi.py` deja listo el entrypoint para Passenger:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

En cPanel apunta la app Python al directorio `foresta-backend/`. No uses `runserver` en produccion.
Manten la carpeta `media/` dentro de `foresta-backend/` entre despliegues; ahi se guardan fotos y archivos subidos. Con `SERVE_MEDIA_FILES=true`, Passenger entrega `/media/...` desde esa carpeta cuando no tienes un alias Apache dedicado.

## Para reducir CPU e I/O

- Sirve `/static/` directamente desde Apache/cPanel cuando sea posible.
- No subas sourcemaps (`*.map`) del frontend al servidor si no necesitas depurar produccion.
- Evita ejecutar importaciones Excel grandes dentro de una peticion web. La API deja jobs en cola y el cron los procesa.
- Manten Swagger/Redoc apagado con `SERVE_API_DOCS=false`.
- Si necesitas auditoria completa por unos minutos, activa `AUDIT_LOG_READS=true`, revisa lo necesario y vuelve a `false`.

## Importaciones por cron

Configura un cron de cPanel cada minuto o cada 2 minutos:

```bash
cd /home/USUARIO/foresta-backend && python manage.py process_import_jobs --max-jobs 1 --max-seconds 45
```

El endpoint de importacion crea `ImportJob` en estado `PENDING`. El comando toma un job, lo marca `RUNNING` y deja el resultado final en el historial. Esto evita que Passenger/cPanel tenga que mantener viva una peticion larga.

Para una carga manual controlada por SSH todavia puedes usar:

```bash
python manage.py import_maestro --file "MAESTRO.xlsx" --dry-run
python manage.py import_maestro --file "MAESTRO.xlsx"
```
