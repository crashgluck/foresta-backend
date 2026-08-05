from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from io import BytesIO
import re

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers


TASK_STATUS_KEY = 'task_status'
TASK_MONTH_KEY = 'task_month'
MONTHLY_ACTIVE_LIGHTS_KEY = 'monthly_active_lights'
MONTHLY_LIGHTS_TO_REPLACE_KEY = 'monthly_lights_to_replace'

TASK_STATUS_PENDING = 'PENDING'
TASK_STATUS_DONE = 'DONE'
TASK_STATUS_LABELS = {
    TASK_STATUS_PENDING: 'Pendiente',
    TASK_STATUS_DONE: 'Realizado',
}


def normalize_task_status(value) -> str:
    status = str(value or TASK_STATUS_PENDING).strip().upper()
    return status if status in TASK_STATUS_LABELS else TASK_STATUS_PENDING


def asset_task_status(asset) -> str:
    properties = asset.properties if isinstance(asset.properties, dict) else {}
    return normalize_task_status(properties.get(TASK_STATUS_KEY))


def parse_report_range(params) -> tuple[date, date, str]:
    month = str(params.get('month') or '').strip()
    if month:
        if not re.match(r'^\d{4}-\d{2}$', month):
            raise serializers.ValidationError({'month': 'Usa formato YYYY-MM.'})
        year, month_number = [int(part) for part in month.split('-')]
        start = date(year, month_number, 1)
        end = date(year + int(month_number == 12), 1 if month_number == 12 else month_number + 1, 1)
        return start, end, month

    date_from = _parse_date(params.get('date_from'), 'date_from')
    date_to = _parse_date(params.get('date_to'), 'date_to')
    if not date_from and not date_to:
        today = timezone.localdate()
        start = today.replace(day=1)
        end = date(today.year + int(today.month == 12), 1 if today.month == 12 else today.month + 1, 1)
        return start, end, start.strftime('%Y-%m')

    start = date_from or date_to.replace(day=1)
    end_inclusive = date_to or start
    if start > end_inclusive:
        raise serializers.ValidationError({'date_to': 'La fecha final debe ser mayor o igual a la inicial.'})
    end = end_inclusive.fromordinal(end_inclusive.toordinal() + 1)
    return start, end, f'{start.isoformat()} al {end_inclusive.isoformat()}'


def _parse_date(value, field_name):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError as exc:
        raise serializers.ValidationError({field_name: 'Usa formato YYYY-MM-DD.'}) from exc


def filter_assets_by_task_status(assets, status_value):
    status = str(status_value or '').strip().upper()
    if status not in TASK_STATUS_LABELS:
        return list(assets)
    return [asset for asset in assets if asset_task_status(asset) == status]


def build_monthly_report_payload(assets, *, params=None):
    params = params or {}
    start, end, period_label = parse_report_range(params)
    task_status_filter = str(params.get('task_status') or '').strip().upper()
    filtered_assets = []

    for asset in assets:
        if not _asset_in_period(asset, start, end):
            continue
        if task_status_filter in TASK_STATUS_LABELS and asset_task_status(asset) != task_status_filter:
            continue
        filtered_assets.append(asset)

    by_category = defaultdict(lambda: _empty_group())
    by_service_type = defaultdict(lambda: _empty_group())
    by_task_status = {status: {'key': status, 'label': label, 'total': 0} for status, label in TASK_STATUS_LABELS.items()}
    by_operational_status = defaultdict(lambda: {'key': '', 'label': '', 'total': 0})

    items = []
    summary = {
        'total_assets': 0,
        'pending_tasks': 0,
        'done_tasks': 0,
        'monthly_active_lights': 0,
        'monthly_lights_to_replace': 0,
        'critical_assets': 0,
        'with_photos': 0,
    }

    for asset in filtered_assets:
        properties = asset.properties if isinstance(asset.properties, dict) else {}
        task_status = asset_task_status(asset)
        active_lights = _int_value(properties.get(MONTHLY_ACTIVE_LIGHTS_KEY))
        lights_to_replace = _int_value(properties.get(MONTHLY_LIGHTS_TO_REPLACE_KEY))
        category_name = asset.category.name if asset.category_id else 'Sin categoria'
        service_type = asset.category.service_type if asset.category_id else 'GENERAL'
        operational_label = asset.get_operational_status_display()

        summary['total_assets'] += 1
        summary['monthly_active_lights'] += active_lights
        summary['monthly_lights_to_replace'] += lights_to_replace
        summary['critical_assets'] += int(asset.criticality == 'CRITICAL')
        summary['with_photos'] += int(bool(asset.photo))
        if task_status == TASK_STATUS_DONE:
            summary['done_tasks'] += 1
        else:
            summary['pending_tasks'] += 1

        _add_to_group(by_category[category_name], category_name, asset, task_status, active_lights, lights_to_replace)
        _add_to_group(by_service_type[service_type], service_type, asset, task_status, active_lights, lights_to_replace)
        by_task_status[task_status]['total'] += 1
        by_operational_status[asset.operational_status]['key'] = asset.operational_status
        by_operational_status[asset.operational_status]['label'] = operational_label
        by_operational_status[asset.operational_status]['total'] += 1

        items.append(
            {
                'id': asset.id,
                'title': asset.title,
                'code': asset.code,
                'category_name': category_name,
                'category_color': asset.category.color if asset.category_id else '#64748b',
                'category_service_type': service_type,
                'task_status': task_status,
                'task_status_label': TASK_STATUS_LABELS[task_status],
                'task_month': properties.get(TASK_MONTH_KEY) or '',
                'monthly_active_lights': active_lights,
                'monthly_lights_to_replace': lights_to_replace,
                'operational_status': asset.operational_status,
                'operational_status_label': operational_label,
                'criticality': asset.criticality,
                'criticality_label': asset.get_criticality_display(),
                'parcela_code': asset.parcela.codigo_parcela if asset.parcela_id else '',
                'last_inspection_date': asset.last_inspection_date.isoformat() if asset.last_inspection_date else '',
                'updated_at': asset.updated_at.isoformat() if asset.updated_at else '',
            }
        )

    completion_rate = 0
    if summary['total_assets']:
        completion_rate = round((summary['done_tasks'] / summary['total_assets']) * 100, 1)
    summary['completion_rate'] = completion_rate

    items.sort(key=lambda item: (item['task_status'] == TASK_STATUS_DONE, item['category_name'], item['title']))

    return {
        'period': {
            'label': period_label,
            'date_from': start.isoformat(),
            'date_to': date.fromordinal(end.toordinal() - 1).isoformat(),
        },
        'summary': summary,
        'by_task_status': list(by_task_status.values()),
        'by_category': sorted(by_category.values(), key=lambda item: (-item['total'], item['label'])),
        'by_service_type': sorted(by_service_type.values(), key=lambda item: (-item['total'], item['label'])),
        'by_operational_status': sorted(by_operational_status.values(), key=lambda item: (-item['total'], item['label'])),
        'items': items,
    }


def _asset_in_period(asset, start: date, end: date) -> bool:
    properties = asset.properties if isinstance(asset.properties, dict) else {}
    task_month = properties.get(TASK_MONTH_KEY)
    if task_month and re.match(r'^\d{4}-\d{2}$', str(task_month)):
        year, month_number = [int(part) for part in str(task_month).split('-')]
        task_date = date(year, month_number, 1)
        return start <= task_date < end

    if asset.last_inspection_date:
        return start <= asset.last_inspection_date < end

    if asset.updated_at:
        return start <= timezone.localtime(asset.updated_at).date() < end

    return False


def _empty_group():
    return {
        'key': '',
        'label': '',
        'total': 0,
        'pending_tasks': 0,
        'done_tasks': 0,
        'monthly_active_lights': 0,
        'monthly_lights_to_replace': 0,
    }


def _add_to_group(group, label, asset, task_status, active_lights, lights_to_replace):
    group['key'] = str(label)
    group['label'] = str(label)
    group['total'] += 1
    group['monthly_active_lights'] += active_lights
    group['monthly_lights_to_replace'] += lights_to_replace
    if task_status == TASK_STATUS_DONE:
        group['done_tasks'] += 1
    else:
        group['pending_tasks'] += 1


def _int_value(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def render_monthly_report_pdf(payload):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise serializers.ValidationError({'detail': 'No fue posible preparar el informe PDF.'}) from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title='Informe mensual de instalaciones',
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ReportTitle', parent=styles['Title'], textColor=colors.HexColor('#14532d'), spaceAfter=6)
    subtitle_style = ParagraphStyle('ReportSubtitle', parent=styles['BodyText'], textColor=colors.HexColor('#475569'), spaceAfter=12)
    section_style = ParagraphStyle('ReportSection', parent=styles['Heading2'], textColor=colors.HexColor('#0f172a'), fontSize=13, spaceBefore=14)

    summary = payload['summary']
    story = [
        Paragraph('Informe mensual de instalaciones', title_style),
        Paragraph(f"Periodo: {payload['period']['label']} ({payload['period']['date_from']} a {payload['period']['date_to']})", subtitle_style),
    ]

    summary_rows = [
        ['Puntos', summary['total_assets'], 'Pendientes', summary['pending_tasks']],
        ['Realizados', summary['done_tasks'], 'Avance', f"{summary['completion_rate']}%"],
        ['Luminarias activas', summary['monthly_active_lights'], 'Por cambiar', summary['monthly_lights_to_replace']],
    ]
    summary_table = Table(summary_rows, colWidths=[4.1 * cm, 2.5 * cm, 4.1 * cm, 2.5 * cm])
    summary_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([summary_table, Spacer(1, 0.3 * cm), Paragraph('Resumen por categoria', section_style)])

    category_rows = [['Categoria', 'Total', 'Pendientes', 'Realizados', 'Activas', 'Cambiar']]
    for row in payload['by_category'][:12]:
        category_rows.append(
            [
                row['label'],
                row['total'],
                row['pending_tasks'],
                row['done_tasks'],
                row['monthly_active_lights'],
                row['monthly_lights_to_replace'],
            ]
        )
    category_table = Table(category_rows, repeatRows=1, colWidths=[5.6 * cm, 1.5 * cm, 2.2 * cm, 2.2 * cm, 1.8 * cm, 1.8 * cm])
    category_table.setStyle(_table_style(colors))
    story.extend([category_table, Spacer(1, 0.2 * cm), Paragraph('Detalle operativo', section_style)])

    item_rows = [['Estado', 'Punto', 'Categoria', 'Parcela', 'Criticidad', 'Ultima insp.']]
    for item in payload['items'][:35]:
        item_rows.append(
            [
                item['task_status_label'],
                item['title'][:34],
                item['category_name'][:24],
                item['parcela_code'] or '-',
                item['criticality_label'],
                item['last_inspection_date'] or '-',
            ]
        )
    item_table = Table(item_rows, repeatRows=1, colWidths=[2.3 * cm, 4.6 * cm, 3.6 * cm, 2.1 * cm, 2.2 * cm, 2.3 * cm])
    item_table.setStyle(_table_style(colors))
    story.append(item_table)

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    filename = f"foresta-informe-mapa-{payload['period']['label']}.pdf".replace(' ', '-')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _table_style(colors):
    from reportlab.platypus import TableStyle

    return TableStyle(
        [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#14532d')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ]
    )
