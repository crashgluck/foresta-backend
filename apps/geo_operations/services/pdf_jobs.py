from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone
from rest_framework import exceptions

from apps.core.cache_utils import get_api_cache_epoch
from apps.geo_operations.models import GeoAsset
from apps.geo_operations.services.geometry import bbox_intersects_filter, parse_bbox
from apps.geo_operations.services.reports import build_monthly_report_payload, render_monthly_report_pdf


PDF_JOB_TIMEOUT_SECONDS = getattr(settings, 'GEO_MONTHLY_REPORT_PDF_JOB_TIMEOUT_SECONDS', 60 * 60)
logger = logging.getLogger(__name__)


def start_monthly_report_pdf_job(params) -> dict:
    normalized_params = _normalize_params(params)
    job_id = _job_id(normalized_params)
    file_path = _job_file_path(job_id)
    status_key = _status_key(job_id)

    if file_path.exists():
        payload = _done_payload(job_id, normalized_params, file_path)
        cache.set(status_key, payload, timeout=PDF_JOB_TIMEOUT_SECONDS)
        return payload

    current_status = cache.get(status_key)
    if current_status and current_status.get('status') == 'done' and file_path.exists():
        return current_status

    return _run_monthly_report_pdf_job(job_id, normalized_params)


def get_monthly_report_pdf_job(job_id: str) -> dict:
    job_id = _clean_job_id(job_id)
    if not job_id:
        raise exceptions.ValidationError({'job_id': 'Parametro requerido.'})

    file_path = _job_file_path(job_id)
    if file_path.exists():
        status_payload = cache.get(_status_key(job_id)) or {}
        params = status_payload.get('params') or {}
        payload = _done_payload(job_id, params, file_path)
        cache.set(_status_key(job_id), payload, timeout=PDF_JOB_TIMEOUT_SECONDS)
        return payload

    status_payload = cache.get(_status_key(job_id))
    if status_payload:
        return status_payload

    return {
        'job_id': job_id,
        'status': 'missing',
        'message': 'El informe ya no esta disponible. Intenta generarlo nuevamente.',
        'download_url': '',
    }


def get_monthly_report_pdf_file(job_id: str) -> tuple[Path, str]:
    job_id = _clean_job_id(job_id)
    if not job_id:
        raise exceptions.ValidationError({'job_id': 'Parametro requerido.'})

    file_path = _job_file_path(job_id)
    if not file_path.exists():
        raise exceptions.NotFound('El informe aun no esta listo o expiro.')

    status_payload = cache.get(_status_key(job_id)) or {}
    filename = status_payload.get('filename') or f'foresta-informe-mapa-{job_id[:12]}.pdf'
    return file_path, filename


def _run_monthly_report_pdf_job(job_id: str, params: dict):
    status_key = _status_key(job_id)
    try:
        cache.set(
            status_key,
            {'job_id': job_id, 'status': 'running', 'message': 'Generando PDF.', 'download_url': '', 'params': params},
            timeout=PDF_JOB_TIMEOUT_SECONDS,
        )
        close_old_connections()
        queryset = _filtered_geo_assets(params)[:5000]
        payload = build_monthly_report_payload(queryset, params=params)
        response = render_monthly_report_pdf(payload)
        file_path = _job_file_path(job_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(response.content)
        done_payload = _done_payload(job_id, params, file_path)
        cache.set(status_key, done_payload, timeout=PDF_JOB_TIMEOUT_SECONDS)
        return done_payload
    except Exception as exc:
        logger.exception('No fue posible generar el PDF mensual de infraestructura. job_id=%s params=%s', job_id, params)
        failed_payload = {
            'job_id': job_id,
            'status': 'failed',
            'message': str(exc) or 'No fue posible generar el PDF.',
            'download_url': '',
            'params': params,
        }
        cache.set(status_key, failed_payload, timeout=PDF_JOB_TIMEOUT_SECONDS)
        return failed_payload
    finally:
        close_old_connections()


def _filtered_geo_assets(params: dict):
    queryset = (
        GeoAsset.objects.select_related('category', 'parcela', 'created_by', 'updated_by')
        .filter(is_deleted=False)
        .order_by('category__sort_order', 'title')
    )

    category_values = _csv_values(params.get('category') or params.get('categories'))
    if category_values:
        numeric_ids = [value for value in category_values if str(value).isdigit()]
        slugs = [value for value in category_values if not str(value).isdigit()]
        category_filter = Q()
        if numeric_ids:
            category_filter |= Q(category_id__in=numeric_ids)
        if slugs:
            category_filter |= Q(category__slug__in=slugs)
        queryset = queryset.filter(category_filter)

    for query_param, field_name in [
        ('geometry_type', 'geometry_type'),
        ('service_type', 'category__service_type'),
        ('status', 'operational_status'),
        ('operational_status', 'operational_status'),
        ('criticality', 'criticality'),
    ]:
        values = _csv_values(params.get(query_param))
        if values:
            queryset = queryset.filter(**{f'{field_name}__in': values})

    is_active = params.get('is_active')
    if is_active in {'true', '1', 'yes'}:
        queryset = queryset.filter(is_active=True)
    elif is_active in {'false', '0', 'no'}:
        queryset = queryset.filter(is_active=False)

    bbox_raw = params.get('bbox')
    if bbox_raw:
        try:
            queryset = bbox_intersects_filter(queryset, parse_bbox(bbox_raw))
        except DjangoValidationError as exc:
            raise exceptions.ValidationError({'bbox': exc.messages}) from exc

    return queryset


def _done_payload(job_id: str, params: dict, file_path: Path) -> dict:
    filename = f"foresta-informe-mapa-{params.get('month') or timezone.localdate().strftime('%Y-%m')}.pdf".replace(' ', '-')
    return {
        'job_id': job_id,
        'status': 'done',
        'message': 'Informe listo.',
        'download_url': 'monthly-report-pdf-download/',
        'filename': filename,
        'size': file_path.stat().st_size if file_path.exists() else 0,
        'params': params,
    }


def _job_id(params: dict) -> str:
    raw = json.dumps({'params': params, 'epoch': get_api_cache_epoch()}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _job_file_path(job_id: str) -> Path:
    cache_dir = Path(getattr(settings, 'GEO_REPORT_CACHE_DIR', Path(settings.BASE_DIR) / '.cache' / 'reports'))
    return cache_dir / f'{_clean_job_id(job_id)}.pdf'


def _status_key(job_id: str) -> str:
    return f'geo:monthly-report-pdf:{_clean_job_id(job_id)}'


def _normalize_params(params) -> dict:
    normalized = {}
    for key, value in params.items():
        if key in {'file_format', 'job_id'}:
            continue
        if isinstance(value, (list, tuple)):
            value = ','.join(str(item) for item in value if item not in {None, ''})
        if value in {None, ''}:
            continue
        normalized[key] = str(value)
    return normalized


def _clean_job_id(job_id: str) -> str:
    return ''.join(char for char in str(job_id or '') if char in '0123456789abcdef')[:64]


def _csv_values(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [item.strip() for item in str(value).split(',') if item.strip()]
