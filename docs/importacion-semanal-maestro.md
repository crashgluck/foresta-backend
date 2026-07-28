# Importacion semanal del maestro Excel

Este documento define el flujo recomendado para cargar semanalmente el archivo maestro en produccion sin pisar datos a ciegas.

## Regla de oro

Usar siempre uno de estos dos caminos:

1. **App web > Importaciones**: subir Excel, ejecutar preview, revisar errores y luego ejecutar carga real en cola.
2. **CLI segura**: usar `weekly_maestro_import`, que hace preflight, preview, umbrales, backup local si la base es SQLite y reporte JSON.

Evitar `import_maestro` directo para la operacion semanal normal. Ese comando sigue existiendo, pero no tiene preflight operativo, backup ni reporte consolidado.

## Que hace el flujo nuevo

El comando `weekly_maestro_import` agrega una capa segura sobre el importador existente:

- Valida que el archivo exista.
- Bloquea ejecuciones si ya hay otro `ImportJob` activo.
- Revisa estructura del Excel y encabezados esperados.
- Ejecuta preview/dry-run antes de tocar datos reales.
- Corta automaticamente si el preview supera el umbral de errores.
- Crea backup de `db.sqlite3` antes del commit cuando la base es SQLite.
- Genera reporte JSON en `reports/imports/`.
- Deja todo auditado en `ImportJob`, `ImportSheetResult`, `ImportIssue` y `ImportRowResult`.

## Perfiles de hojas

`weekly` es el perfil recomendado para carga semanal:

```text
Mora GC
DESUDAS AyS
MORA CONVENIO
Cortes Vigentes
ANOTACIONES
HISTORICO AYS
```

Otros perfiles disponibles:

```text
owners    Datos_Propietarios, OTROS DUEÑOS, RESIDENTES, PPU_LOGOS
finance   Mora GC, DESUDAS AyS, MORA CONVENIO, Multas-Convenios impagas
services  Cortes Vigentes, HISTORICO AYS, ANOTACIONES
works     OBRAS
full      Todas las hojas soportadas
```

Para sobrescribir el perfil:

```powershell
python manage.py weekly_maestro_import --file "C:\ruta\MAESTRO.xlsx" --mode preview --sheets "Mora GC,Cortes Vigentes"
```

## Flujo recomendado por consola

Entrar al backend:

```powershell
cd C:\Users\crisv\Programacion\foresta-comunidad\backend\foresta-backend
.\.venv\Scripts\activate
```

Preview semanal:

```powershell
python manage.py weekly_maestro_import --file "C:\ruta\MAESTRO.xlsx" --mode preview --profile weekly
```

Si el preview termina sin errores, ejecutar carga real:

```powershell
python manage.py weekly_maestro_import --file "C:\ruta\MAESTRO.xlsx" --mode commit --profile weekly
```

Modo automatico, solo recomendado cuando el archivo ya fue revisado:

```powershell
python manage.py weekly_maestro_import --file "C:\ruta\MAESTRO.xlsx" --mode auto --profile weekly
```

`auto` ejecuta preview y solo hace commit si el preview queda dentro de los umbrales.

## Umbrales

Por defecto se permite:

```text
max-errors = 0
max-warnings = sin limite
```

Ejemplo estricto:

```powershell
python manage.py weekly_maestro_import --file "C:\ruta\MAESTRO.xlsx" --mode auto --profile weekly --max-errors 0 --max-warnings 20
```

Ejemplo tolerante:

```powershell
python manage.py weekly_maestro_import --file "C:\ruta\MAESTRO.xlsx" --mode auto --profile weekly --max-errors 5
```

## Reportes

Cada ejecucion genera un JSON en:

```text
reports/imports/
```

El reporte contiene:

- Archivo y hash SHA-256.
- Perfil y hojas seleccionadas.
- Resultado de estructura por hoja.
- Job de preview.
- Job de commit, si aplica.
- Totales insertados, actualizados, omitidos, errores y advertencias.
- Muestra de incidencias.
- Ruta del backup SQLite, si se creo.

Si el comando falla por preflight o preview, tambien deja reporte con `gate_errors`.

## Produccion con app web y cola

En cPanel o Passenger conviene evitar requests largas. El flujo web recomendado es:

1. Entrar a la app con usuario `OPERADOR` o superior.
2. Ir a `Admin > Importaciones`.
3. Subir Excel.
4. Ejecutar preview.
5. Revisar errores/advertencias.
6. Ejecutar carga real.
7. Dejar cron procesando jobs pendientes:

```bash
python manage.py process_import_jobs --max-jobs 1 --max-seconds 45
```

Frecuencia sugerida del cron:

```text
cada 1 minuto mientras haya importaciones pendientes
```

## Produccion por cron sin app web

Si se quiere automatizar una carga semanal desde un archivo fijo:

```bash
cd /ruta/foresta-backend
source ../.venv/bin/activate
python manage.py weekly_maestro_import --file "/ruta/imports/MAESTRO_SEMANAL.xlsx" --mode auto --profile weekly --max-errors 0
```

Guardar los Excel entrantes con fecha:

```text
imports/maestro/2026-07-27_MAESTRO.xlsx
```

No reemplazar el archivo anterior hasta confirmar que el reporte de la nueva carga quedo correcto.

## Recuperacion

Si la base es SQLite, el comando crea backup antes del commit en:

```text
backups/imports/
```

Para restaurar manualmente:

1. Detener la app.
2. Copiar el backup sobre `db.sqlite3`.
3. Levantar la app.
4. Revisar `/api/v1/imports/jobs/`.

Si no se quiere restaurar toda la base, existe rollback logico de registros creados por un job:

```powershell
python manage.py rollback_import_job <JOB_ID>
python manage.py rollback_import_job <JOB_ID> --execute --confirm <JOB_ID>
```

Importante: el rollback logico es util para registros creados en la ventana del job. No garantiza deshacer todos los cambios de campos actualizados. Para un desastre grande, el backup/snapshot de base es mas seguro.

## Consideraciones del importador

El importador actual trabaja como **upsert/append seguro**:

- Crea parcelas/personas/registros nuevos.
- Actualiza ciertos registros existentes cuando encuentra la misma llave.
- Omite duplicados detectados.
- No elimina automaticamente registros que desaparecen del Excel.

Eso es intencional para evitar perdida accidental de datos. Si el Excel debe ser la unica fuente de verdad y se necesita desactivar registros ausentes, hay que agregar una etapa de reconciliacion controlada.

## Diagnostico rapido

Ver ultimos jobs:

```powershell
python manage.py shell -c "from apps.data_imports.models import ImportJob; [print(j.id, j.status, j.dry_run, j.total_inserted, j.total_updated, j.total_errors, j.total_warnings, j.started_at, j.finished_at) for j in ImportJob.objects.order_by('-started_at')[:10]]"
```

Cancelar un job desde API/app o por shell si quedo detenido:

```powershell
python manage.py shell -c "from django.utils import timezone; from apps.data_imports.models import ImportJob, ImportStatus; j=ImportJob.objects.get(id='<JOB_ID>'); j.status=ImportStatus.CANCELLED; j.finished_at=timezone.now(); j.save(update_fields=['status','finished_at'])"
```

Importar una sola hoja para aislar lentitud:

```powershell
python manage.py weekly_maestro_import --file "C:\ruta\MAESTRO.xlsx" --mode preview --sheets "HISTORICO AYS"
```

