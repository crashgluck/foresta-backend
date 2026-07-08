# Backend Parcelas API (Django + DRF)

Backend profesional para gestion de parcelas/lotes, propietarios, residentes, vehiculos, deudas, servicios, cortes, anotaciones y obras.

La entidad central del negocio es la **parcela** (`LETRA-NUMERO`, por ejemplo `N-19`, `C-40B`).

## 1. Stack

- Python 3.14+
- Django 6
- Django REST Framework
- JWT (SimpleJWT)
- drf-spectacular (OpenAPI / Swagger)
- django-filter
- django-cors-headers
- openpyxl (importacion Excel)

## 2. Arquitectura de apps

- `apps.accounts`: usuario custom, roles, autenticacion JWT, perfil
- `apps.parcels`: entidad central Parcela
- `apps.people`: personas, propietarios/coproprietarios, residentes
- `apps.vehicles`: vehiculos
- `apps.finance`: deudas GC, deudas servicios, convenios, multas
- `apps.utilities`: cortes vigentes e historico servicios
- `apps.notes`: anotaciones administrativas
- `apps.works`: estado/obras por parcela
- `apps.access_control`: accesos de porteria y lista negra
- `apps.maps_app`: geometrias de parcelas, objetivos y visitas
- `apps.acquisitions`: controles remotos, tarjetas RFID y logos vehiculares
- `apps.missions`: misiones, vuelos de dron y reportes operativos
- `apps.supervisor`: turnos, rondas y notificaciones/multas operativas
- `apps.data_imports`: pipeline de importacion Excel, logs, incidencias
- `apps.api`: router API v1 y dashboard
- `apps.core`: base models, soft-delete, auditoria, normalizacion, permisos

## 3. Roles y permisos

Roles definidos (`accounts.User.role`):

- `SUPERADMIN`
- `ADMINISTRADOR`
- `OPERADOR`
- `CONSULTA`

Regla general:

- `CONSULTA`: solo lectura
- `OPERADOR`: crea/edita dominio y puede ejecutar importaciones
- `ADMINISTRADOR`: gestion avanzada (incluye usuarios)
- `SUPERADMIN`: control total (incluye eliminar usuarios admin/superadmin)

## 4. Endpoints principales

Base URL: `/api/v1/`

### Auth y usuarios

- `POST /auth/register/`
- `POST /auth/login/`
- `POST /auth/refresh/`
- `POST /auth/logout/`
- `GET /auth/me/`
- `POST /auth/change-password/`
- `GET /roles/`
- `CRUD /users/`

### Dominio

- `CRUD /parcelas/`
- `GET /parcelas/{id}/ficha-consolidada/`
- `GET /parcelas/by-code/{codigo}/ficha-consolidada/`
- `CRUD /personas/`
- `CRUD /propietarios/`
- `CRUD /residentes/`
- `CRUD /vehiculos/`
- `CRUD /deudas-gc/`
- `CRUD /deudas-servicios/`
- `CRUD /convenios/`
- `CRUD /multas/`
- `CRUD /movimientos-financieros/`
- `CRUD /cortes/`
- `CRUD /servicios-historico/`
- `CRUD /anotaciones/`
- `CRUD /obras/`
- `GET /dashboard/resumen/`
- `CRUD /access/access-records/`
- `CRUD /access/blacklist/`
- `GET /maps/owners-map/`
- `GET /maps/parcel-options/`
- `CRUD /maps/objectives/`
- `CRUD /maps/visits/`
- `CRUD /missions/missions/`
- `CRUD /missions/drone-flights/`
- `CRUD /missions/mission-reports/`
- `CRUD /acquisitions/remote-controls/`
- `CRUD /acquisitions/rfid-cards/`
- `CRUD /acquisitions/vehicle-logos/`
- `CRUD /supervisor/shifts/`
- `CRUD /supervisor/rounds/`
- `CRUD /supervisor/notifications/`
- `GET /supervisor/notifications/export_csv/`
- `GET /iot/components/`
- `POST /iot/components/{component_id}/on/`
- `POST /iot/components/{component_id}/off/`
- `POST /iot/components/{component_id}/pulse/`

### Importaciones

- `GET /imports/jobs/`
- `GET /imports/jobs/{id}/`
- `POST /imports/jobs/run/`
- `GET /imports/issues/`

## 5. Documentacion API

- OpenAPI JSON: `/api/schema/`
- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`

## 6. Instalacion

Desde `backend/`:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

Copiar variables de entorno:

```bash
cp .env.example .env
```

## 7. Variables de entorno clave

Ver `.env.example`.

Para hosting compartido/cPanel, revisar tambien `CPANEL_OPTIMIZATION.md`.

Importantes:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DB_ENGINE` (`sqlite` o `postgres`)
- `CORS_ALLOWED_ORIGINS`
- `JWT_ACCESS_MINUTES`
- `JWT_REFRESH_DAYS`

Integracion Nodotech IoT:

- `NODOTECH_API_BASE_URL`
- `NODOTECH_EMAIL`
- `NODOTECH_PASSWORD`
- `NODOTECH_REQUEST_TIMEOUT`
- `NODOTECH_DEFAULT_PULSE_MS`
- `NODOTECH_ACCESS_TOKEN_CACHE_SECONDS`
- `NODOTECH_REFRESH_TOKEN_CACHE_SECONDS`

Las credenciales Nodotech son de uso exclusivo del backend y no deben exponerse al frontend.

## 8. Migraciones y servidor

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

## 9. Crear usuario administrativo inicial

```bash
python manage.py seed_initial_data --email admin@example.com --password "ClaveSegura123"
```

## 10. Importar Excel maestro

En produccion/cPanel, la API deja las importaciones reales en cola (`PENDING`) y un cron ejecuta el worker:

```bash
python manage.py process_import_jobs --max-jobs 1 --max-seconds 45
```

Esto evita que Passenger mantenga una peticion HTTP larga mientras se procesa el Excel.

### Dry-run (sin persistir)

```bash
python manage.py import_maestro --file "C:\ruta\MAESTRO.xlsx" --dry-run
```

### Importacion real

```bash
python manage.py import_maestro --file "C:\ruta\MAESTRO.xlsx"
```

### Importacion parcial por hojas

```bash
python manage.py import_maestro --file "C:\ruta\MAESTRO.xlsx" --sheets "Datos_Propietarios,RESIDENTES,PPU_LOGOS"
```

Hojas recomendadas para actualizacion semanal:

```bash
python manage.py import_maestro --file "C:\ruta\MAESTRO.xlsx" --sheets "Mora GC,DESUDAS AyS,MORA CONVENIO,Cortes Vigentes,ANOTACIONES,HISTORICO AYS"
```

## 10.1 Importar sistema legacy (frontend/backend anterior)

```bash
python manage.py import_legacy_system
```

Opcionalmente:

```bash
python manage.py import_legacy_system --legacy-db "C:\ruta\legacy\db.sqlite3" --modules "owners,missions,drone_flights,acquisitions"
```

## 10.2 Seed financiero para dashboard (datos de prueba)

Genera ingresos/egresos realistas para poblar KPIs y series temporales del dashboard:

```bash
python manage.py seed_dashboard_finance --days 90 --seed 42
```

Opcionalmente limpiar antes de generar:

```bash
python manage.py seed_dashboard_finance --days 120 --truncate
```

## 11. Estrategia de importacion implementada

- Pipeline por hojas con parser por dominio
- Normalizacion de parcela (`n19`, `N 19`, ` N-019 ` -> `N-19`)
- Tolerancia a datos incompletos
- `dry-run` para previsualizar impacto
- Upsert/actualizacion donde aplica
- Jobs en cola para produccion/cPanel mediante `process_import_jobs`
- Corte temprano de filas vacias para evitar hojas Excel con dimensiones infladas
- Trazabilidad compacta: errores/warnings por fila y resumen agregado para filas exitosas
- Registro de trazabilidad:
  - `ImportJob`
  - `ImportSheetResult`
  - `ImportIssue`
  - `ImportRowResult` para errores, advertencias y, si se activa `IMPORT_LOG_SUCCESS_ROWS`, tambien acciones exitosas

Hojas soportadas:

- `Datos_Propietarios`
- `OTROS DUEÑOS`
- `RESIDENTES`
- `PPU_LOGOS`
- `Mora GC`
- `DESUDAS AyS`
- `MORA CONVENIO`
- `Multas-Convenios impagas`
- `Cortes Vigentes`
- `HISTORICO AYS`
- `ANOTACIONES`
- `OBRAS`

## 12. Auditoria y calidad

- `created_at`, `updated_at`
- `created_by`, `updated_by`
- soft delete en entidades de dominio (`is_deleted`, `deleted_at`)
- paginacion, filtros, busqueda y ordenamiento global en API

## 13. Tests

Ejecutar:

```bash
python manage.py test
```

Incluye pruebas de:

- autenticacion JWT (registro/login/cambio de clave)
- permisos por rol
- normalizacion de codigo de parcela
- pipeline base de importacion en modo dry-run

## 14. Guia para React / React Native

- Usar `POST /auth/login/` para obtener `access` + `refresh`
- Enviar `Authorization: Bearer <access>`
- Renovar token con `POST /auth/refresh/`
- Consumir la ficha de parcela desde:
  - `/parcelas/{id}/ficha-consolidada/`
  - o `/parcelas/by-code/{codigo}/ficha-consolidada/`

Recomendacion frontend:

- mantener cliente HTTP centralizado con interceptor para refresh token
- usar paginacion server-side en tablas
- usar filtros por query params para vistas operativas

Dashboard:

- Endpoint: `GET /dashboard/resumen/`
- Query params soportados:
  - `preset=today|last_7_days|last_30_days|this_month|custom`
  - `date_from=YYYY-MM-DD` (cuando `preset=custom`)
  - `date_to=YYYY-MM-DD` (cuando `preset=custom`)
  - `parcel_status=ACTIVA|INACTIVA|SUSPENDIDA` (opcional)
  - `parcel_letter=A|B|N|...` (opcional)

## 15. Mejoras futuras sugeridas

1. Versionado formal de API (`/api/v2`) cuando haya cambios breaking.
2. Historial de cambios detallado por entidad (event sourcing ligero o django-simple-history).
3. Celery + Redis solo si mas adelante se migra desde cPanel a un servidor con workers persistentes.
4. Motor de conciliacion de duplicados de personas con reglas mas avanzadas.
5. Dashboard con KPIs historicos y alertas proactivas.
