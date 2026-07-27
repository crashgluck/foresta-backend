from __future__ import annotations

from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.http import HttpResponse

from apps.geo_operations.models import GeoAsset

KML_CONTENT_TYPE = 'application/vnd.google-earth.kml+xml'
KMZ_CONTENT_TYPE = 'application/vnd.google-earth.kmz'


def _kml_color(hex_color: str) -> str:
    value = (hex_color or '#2563eb').strip().lstrip('#')
    if len(value) == 3:
        value = ''.join(char * 2 for char in value)
    if len(value) == 8:
        value = value[-6:]
    if len(value) != 6:
        value = '2563eb'
    red, green, blue = value[0:2], value[2:4], value[4:6]
    return f'ff{blue}{green}{red}'.lower()


def _coordinates(position):
    return f'{position[0]},{position[1]},0'


def _geometry_to_kml(geometry: dict) -> str:
    geo_type = geometry.get('type')
    coords = geometry.get('coordinates')
    if geo_type == 'Point':
        return f'<Point><coordinates>{_coordinates(coords)}</coordinates></Point>'
    if geo_type == 'LineString':
        joined = ' '.join(_coordinates(position) for position in coords)
        return f'<LineString><tessellate>1</tessellate><coordinates>{joined}</coordinates></LineString>'
    if geo_type == 'Polygon':
        ring = coords[0]
        joined = ' '.join(_coordinates(position) for position in ring)
        return (
            '<Polygon><tessellate>1</tessellate><outerBoundaryIs><LinearRing>'
            f'<coordinates>{joined}</coordinates>'
            '</LinearRing></outerBoundaryIs></Polygon>'
        )
    return ''


def _asset_description(asset: GeoAsset) -> str:
    parts = [
        ('Categoria', asset.category.name),
        ('Estado', asset.get_operational_status_display()),
        ('Criticidad', asset.get_criticality_display()),
        ('Codigo', asset.code),
        ('Parcela', asset.parcela.codigo_parcela if asset.parcela_id else ''),
        ('Descripcion', asset.description),
        ('Observaciones', asset.observations),
        ('Vertices', asset.vertex_count),
        ('Longitud m', asset.length_m),
        ('Superficie m2', asset.area_m2),
    ]
    rows = ''.join(f'<tr><th>{escape(str(label))}</th><td>{escape(str(value))}</td></tr>' for label, value in parts if value not in ['', None])
    return f'<![CDATA[<table>{rows}</table>]]>'


def build_kml(assets, *, document_name: str = 'Infraestructura Foresta') -> str:
    placemarks = []
    for asset in assets:
        color = _kml_color(asset.category.color)
        geometry = _geometry_to_kml(asset.geometry)
        if not geometry:
            continue
        placemarks.append(
            f'''
            <Placemark>
              <name>{escape(asset.title)}</name>
              <description>{_asset_description(asset)}</description>
              <Style>
                <IconStyle><color>{color}</color><scale>1.1</scale></IconStyle>
                <LineStyle><color>{color}</color><width>3</width></LineStyle>
                <PolyStyle><color>55{color[2:]}</color></PolyStyle>
              </Style>
              <ExtendedData>
                <Data name="category"><value>{escape(asset.category.slug)}</value></Data>
                <Data name="status"><value>{escape(asset.operational_status)}</value></Data>
                <Data name="criticality"><value>{escape(asset.criticality)}</value></Data>
                <Data name="geometry_type"><value>{escape(asset.geometry_type)}</value></Data>
              </ExtendedData>
              {geometry}
            </Placemark>
            '''
        )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{escape(document_name)}</name>
    {''.join(placemarks)}
  </Document>
</kml>
'''


def export_response(assets, *, file_stem: str, export_format: str = 'kml') -> HttpResponse:
    materialized_assets = list(assets)
    kml = build_kml(materialized_assets)
    safe_stem = ''.join(char if char.isalnum() or char in {'-', '_'} else '-' for char in file_stem).strip('-') or 'infraestructura'

    if export_format == 'kmz':
        buffer = BytesIO()
        with ZipFile(buffer, 'w', compression=ZIP_DEFLATED) as archive:
            archive.writestr('doc.kml', kml.encode('utf-8'))
        response = HttpResponse(buffer.getvalue(), content_type=KMZ_CONTENT_TYPE)
        response['Content-Disposition'] = f'attachment; filename="{safe_stem}.kmz"'
        return response

    response = HttpResponse(kml, content_type=KML_CONTENT_TYPE)
    response['Content-Disposition'] = f'attachment; filename="{safe_stem}.kml"'
    return response
