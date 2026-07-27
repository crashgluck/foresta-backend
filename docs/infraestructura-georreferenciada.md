# Infraestructura georreferenciada

Modulo para registrar y administrar infraestructura u objetivos operacionales sobre mapa:
canales, grifos, luminarias, pozos, camaras, lineas electricas, tuberias,
portones, postes, zonas de riesgo y otros activos.

## Arquitectura

- Backend: app Django `apps.geo_operations`.
- Frontend: ruta React `/mapa/infraestructura`.
- Mapa: se reutiliza `leaflet` y `react-leaflet`.
- Base de datos: compatible con MySQL y SQLite, sin PostGIS requerido.
- Geometria: GeoJSON en `JSONField` con bbox numerico indexado.
- Auditoria: `BaseDomainModel` (`created_by`, `updated_by`, `is_deleted`) y `GeoAssetChangeLog`.
- Permisos: roles existentes.

## Permisos

- Ver categorias y elementos: `CONSULTA`.
- Crear/editar elementos: `OPERADOR`.
- Eliminar elementos y administrar categorias: `ADMINISTRADOR`.
- Exportar KML/KMZ: `CONSULTA`.

## Migraciones y categorias iniciales

```powershell
python manage.py migrate geo_operations
```

La migracion `0002_seed_initial_categories` carga categorias iniciales de forma idempotente.
Tambien puede ejecutarse manualmente:

```powershell
python manage.py seed_geo_categories
```

## Endpoints

- `GET /api/v1/geo/categories/`
- `POST /api/v1/geo/categories/`
- `PATCH /api/v1/geo/categories/{id}/`
- `GET /api/v1/geo/assets/`
- `POST /api/v1/geo/assets/`
- `PATCH /api/v1/geo/assets/{id}/`
- `DELETE /api/v1/geo/assets/{id}/`
- `GET /api/v1/geo/assets/map/?bbox=west,south,east,north`
- `GET /api/v1/geo/assets/choices/`
- `GET /api/v1/geo/assets/export/?file_format=kml`
- `GET /api/v1/geo/assets/export/?file_format=kmz`

Filtros soportados en elementos:

- `bbox=west,south,east,north`
- `categories=1,2` o `categories=grifos-incendio,pozos`
- `geometry_type=POINT|LINE|POLYGON`
- `operational_status=ACTIVE|MAINTENANCE|REVIEW|OUT_OF_SERVICE|UNKNOWN`
- `criticality=LOW|MEDIUM|HIGH|CRITICAL`
- `parcela={id}`
- `search={texto}`

## GeoJSON soportado

Punto:

```json
{ "type": "Point", "coordinates": [-70.66, -33.45] }
```

Linea:

```json
{ "type": "LineString", "coordinates": [[-70.66, -33.45], [-70.65, -33.44]] }
```

Poligono:

```json
{
  "type": "Polygon",
  "coordinates": [[[-70.66, -33.45], [-70.65, -33.45], [-70.65, -33.44], [-70.66, -33.45]]]
}
```

Las coordenadas GeoJSON se guardan como `[longitud, latitud]`.

## Exportacion KML/KMZ

El backend genera KML directamente y KMZ como ZIP con `doc.kml`.
La exportacion conserva nombre, categoria, estado, criticidad, color, tipo de geometria,
metadata relevante y coordenadas compatibles con Google Earth/QGIS.

Ejemplos:

```powershell
curl -H "Authorization: Bearer <token>" `
  "http://localhost:8000/api/v1/geo/assets/export/?file_format=kml&categories=grifos-incendio" `
  -o foresta-grifos.kml
```

```powershell
curl -H "Authorization: Bearer <token>" `
  "http://localhost:8000/api/v1/geo/assets/export/?file_format=kmz&bbox=-70.7,-33.5,-70.6,-33.4" `
  -o foresta-visible.kmz
```

## Uso en frontend

1. Abrir `/mapa/infraestructura`.
2. Activar capas en el panel lateral.
3. Seleccionar `Agregar elemento`.
4. Elegir categoria y tipo de geometria permitido.
5. Dibujar sobre el mapa.
6. Usar `Deshacer`, arrastrar vertices o doble clic sobre vertices para eliminarlos.
7. Completar la ficha y guardar.
8. Exportar filtros visibles como KML o KMZ.

## Validaciones

El backend valida:

- Tipo GeoJSON soportado.
- Coherencia categoria/geometria.
- Rangos de latitud y longitud.
- Minimo de vertices.
- Cierre de poligonos.
- Limite de vertices.
- Permisos por rol.

## Pruebas

```powershell
python manage.py test apps.geo_operations
python manage.py test
```

Frontend:

```powershell
npm run build
```

## Notas tecnicas

- No se agregaron dependencias nuevas.
- No se cambio la base de datos a PostGIS.
- Si en el futuro se migra a PostGIS, la logica esta concentrada en
  `apps.geo_operations.services.geometry` y los campos bbox permiten transicion gradual.
