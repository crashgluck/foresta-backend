from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from django.core.exceptions import ValidationError


SUPPORTED_GEOJSON_TYPES = {'Point', 'LineString', 'Polygon'}
GEOMETRY_TYPE_TO_GEOJSON = {
    'POINT': 'Point',
    'LINE': 'LineString',
    'POLYGON': 'Polygon',
}
GEOJSON_TYPE_TO_GEOMETRY_TYPE = {value: key for key, value in GEOMETRY_TYPE_TO_GEOJSON.items()}
MAX_GEOMETRY_VERTICES = 5000
EARTH_RADIUS_M = 6371008.8


@dataclass(frozen=True)
class GeometrySummary:
    geometry_type: str
    bbox: tuple[float, float, float, float]
    center: tuple[float, float]
    vertex_count: int
    length_m: float
    perimeter_m: float
    area_m2: float


def _as_float(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f'{label} debe ser numerico.')
    if not math.isfinite(number):
        raise ValidationError(f'{label} debe ser finito.')
    return number


def validate_position(position, *, path: str = 'coordinates') -> tuple[float, float]:
    if not isinstance(position, (list, tuple)) or len(position) < 2:
        raise ValidationError(f'{path} debe contener [longitud, latitud].')

    lng = _as_float(position[0], f'{path}.longitud')
    lat = _as_float(position[1], f'{path}.latitud')
    if lng < -180 or lng > 180:
        raise ValidationError(f'{path}.longitud fuera de rango [-180, 180].')
    if lat < -90 or lat > 90:
        raise ValidationError(f'{path}.latitud fuera de rango [-90, 90].')
    return lng, lat


def _validate_point(coordinates) -> list[tuple[float, float]]:
    return [validate_position(coordinates)]


def _validate_line(coordinates) -> list[tuple[float, float]]:
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValidationError('LineString requiere al menos 2 vertices.')
    return [validate_position(position, path=f'coordinates[{index}]') for index, position in enumerate(coordinates)]


def _validate_polygon(coordinates) -> list[tuple[float, float]]:
    if not isinstance(coordinates, list) or not coordinates:
        raise ValidationError('Polygon requiere al menos un anillo exterior.')

    exterior = coordinates[0]
    if not isinstance(exterior, list) or len(exterior) < 4:
        raise ValidationError('El anillo exterior del poligono requiere al menos 4 vertices.')

    positions = [validate_position(position, path=f'coordinates[0][{index}]') for index, position in enumerate(exterior)]
    if positions[0] != positions[-1]:
        raise ValidationError('El poligono debe estar cerrado: el primer y ultimo vertice deben coincidir.')
    return positions


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lng1, lat1 = map(math.radians, a)
    lng2, lat2 = map(math.radians, b)
    delta_lat = lat2 - lat1
    delta_lng = lng2 - lng1
    hav = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(hav))


def _line_length_m(positions: list[tuple[float, float]]) -> float:
    return sum(_distance_m(positions[index - 1], positions[index]) for index in range(1, len(positions)))


def _polygon_area_m2(positions: list[tuple[float, float]]) -> float:
    if len(positions) < 4:
        return 0.0

    center_lat = math.radians(sum(lat for _, lat in positions) / len(positions))
    projected: list[tuple[float, float]] = []
    for lng, lat in positions:
        x = math.radians(lng) * EARTH_RADIUS_M * math.cos(center_lat)
        y = math.radians(lat) * EARTH_RADIUS_M
        projected.append((x, y))

    area = 0.0
    for index in range(len(projected) - 1):
        x1, y1 = projected[index]
        x2, y2 = projected[index + 1]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2


def _bbox(positions: Iterable[tuple[float, float]]) -> tuple[float, float, float, float]:
    values = list(positions)
    lngs = [position[0] for position in values]
    lats = [position[1] for position in values]
    return min(lngs), min(lats), max(lngs), max(lats)


def validate_geojson_geometry(geometry, *, allowed_geometry_type: str = 'ANY') -> GeometrySummary:
    if not isinstance(geometry, dict):
        raise ValidationError('La geometria debe ser un objeto GeoJSON.')

    if geometry.get('type') == 'Feature':
        geometry = geometry.get('geometry')
        if not isinstance(geometry, dict):
            raise ValidationError('La Feature GeoJSON no contiene una geometria valida.')

    geojson_type = geometry.get('type')
    coordinates = geometry.get('coordinates')
    if geojson_type not in SUPPORTED_GEOJSON_TYPES:
        raise ValidationError('Tipo GeoJSON no soportado. Usa Point, LineString o Polygon.')

    geometry_type = GEOJSON_TYPE_TO_GEOMETRY_TYPE[geojson_type]
    if allowed_geometry_type and allowed_geometry_type != 'ANY' and allowed_geometry_type != geometry_type:
        raise ValidationError(f'La categoria permite geometria {allowed_geometry_type}, no {geometry_type}.')

    if geojson_type == 'Point':
        positions = _validate_point(coordinates)
        length_m = 0.0
        perimeter_m = 0.0
        area_m2 = 0.0
    elif geojson_type == 'LineString':
        positions = _validate_line(coordinates)
        length_m = _line_length_m(positions)
        perimeter_m = 0.0
        area_m2 = 0.0
    else:
        positions = _validate_polygon(coordinates)
        length_m = 0.0
        perimeter_m = _line_length_m(positions)
        area_m2 = _polygon_area_m2(positions)

    if len(positions) > MAX_GEOMETRY_VERTICES:
        raise ValidationError(f'La geometria supera el maximo de {MAX_GEOMETRY_VERTICES} vertices.')

    min_lng, min_lat, max_lng, max_lat = _bbox(positions)
    return GeometrySummary(
        geometry_type=geometry_type,
        bbox=(min_lng, min_lat, max_lng, max_lat),
        center=((min_lng + max_lng) / 2, (min_lat + max_lat) / 2),
        vertex_count=len(positions),
        length_m=round(length_m, 2),
        perimeter_m=round(perimeter_m, 2),
        area_m2=round(area_m2, 2),
    )


def parse_bbox(raw_bbox: str | None) -> tuple[float, float, float, float] | None:
    if not raw_bbox:
        return None

    parts = [part.strip() for part in raw_bbox.split(',')]
    if len(parts) != 4:
        raise ValidationError('bbox debe tener formato west,south,east,north.')

    west, south, east, north = [_as_float(part, 'bbox') for part in parts]
    if west < -180 or east > 180 or south < -90 or north > 90 or west > east or south > north:
        raise ValidationError('bbox fuera de rango o invertido.')
    return west, south, east, north


def bbox_intersects_filter(queryset, bbox: tuple[float, float, float, float]):
    west, south, east, north = bbox
    return queryset.filter(max_lng__gte=west, min_lng__lte=east, max_lat__gte=south, min_lat__lte=north)
