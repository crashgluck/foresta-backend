from io import BytesIO
from xml.sax.saxutils import escape

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


STATUS_LABELS = {
    'DETECTED': 'Detectada',
    'EVALUATED': 'Evaluada',
    'ASSIGNED': 'Asignada',
    'IN_PROGRESS': 'En ejecucion',
    'EXECUTED': 'Ejecutada',
    'VERIFICATION': 'En verificacion',
    'CLOSED': 'Cerrada',
    'BLOCKED': 'Bloqueada',
    'CANCELLED': 'Cancelada',
}

PRIORITY_LABELS = {
    'LOW': 'Baja',
    'MEDIUM': 'Media',
    'HIGH': 'Alta',
    'CRITICAL': 'Critica',
}

FILTER_LABELS = {
    'area': 'Area',
    'bbox': 'Area visible del mapa',
    'blocked': 'Bloqueadas',
    'date_from': 'Desde',
    'date_to': 'Hasta',
    'month': 'Mes',
    'overdue': 'Vencidas',
    'priority': 'Prioridad',
    'search': 'Busqueda',
    'status': 'Estado',
    'year': 'Ano',
}


def _format_datetime(value):
    if not value:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    return str(value)[:10]


def _section_title(text, styles):
    return [Spacer(1, 10), Paragraph(text, styles['Heading2']), Spacer(1, 6)]


def _display_status(value):
    return STATUS_LABELS.get(value, value or '')


def _display_priority(value):
    return PRIORITY_LABELS.get(value, value or '')


def _display_filter(key, value):
    label = FILTER_LABELS.get(key, key.replace('_', ' ').title())
    if key == 'status':
        value = _display_status(value)
    elif key == 'priority':
        value = _display_priority(value)
    elif isinstance(value, bool):
        value = 'Si' if value else 'No'
    return f'{label}: {value}'


def _paragraph(text, style, *, limit=None):
    value = str(text or '')
    if limit:
        value = value[:limit]
    return Paragraph(escape(value), style)


def _code_paragraph(code, style):
    value = str(code or '')
    parts = value.split('-', 2)
    if len(parts) >= 3:
        value = f'{parts[0]}-{parts[1]}<br/>-{parts[2]}'
    return Paragraph(value, style)


def _task_table(tasks, styles, *, empty_text='Sin tareas para esta seccion.'):
    if not tasks:
        return [Paragraph(empty_text, styles['BodyText'])]
    rows = [['Codigo', 'Titulo', 'Estado', 'Prioridad', 'Area', 'Instalacion', 'Ejecutor', 'Vence']]
    for task in tasks:
        rows.append(
            [
                _code_paragraph(task['code'], styles['BodyText']),
                _paragraph(task['title'], styles['BodyText'], limit=90),
                _display_status(task['status']),
                _display_priority(task['priority']),
                _paragraph(task['area'], styles['BodyText'], limit=35),
                _paragraph(task['geo_asset'], styles['BodyText'], limit=70),
                _paragraph(task['executor'], styles['BodyText'], limit=70),
                _format_datetime(task.get('due_at')),
            ]
        )
    table = Table(rows, repeatRows=1, colWidths=[92, 168, 76, 62, 82, 112, 118, 70])
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#d1d5db')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('LEADING', (0, 0), (-1, -1), 9),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]
        )
    )
    return [table]


def render_operation_report_pdf(payload, *, filename='reporte-operacional.pdf'):
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    period = payload.get('period') or {}
    period_text = f"{(period.get('start') or 'inicio')[:10]} a {(period.get('end') or 'actual')[:10]}"
    elements = [
        Paragraph('Informe operacional', styles['Title']),
        Paragraph('Comunidad La Foresta de Zapallar', styles['Heading2']),
        Spacer(1, 10),
        Paragraph(f'Periodo informado: {period_text}', styles['Normal']),
        Paragraph(f"Fecha de generacion: {(payload.get('generated_at') or '')[:19]}", styles['Normal']),
        Paragraph(f"Generado por: {payload.get('generated_by') or 'No informado'}", styles['Normal']),
        Spacer(1, 12),
    ]

    filters_text = '; '.join(_display_filter(key, value) for key, value in sorted(payload.get('filters', {}).items()) if value) or 'Sin criterios adicionales'
    elements.append(Paragraph(f'Criterios aplicados: {filters_text}', styles['Normal']))
    elements.append(Spacer(1, 12))

    summary = payload.get('summary', {})
    summary_data = [
        ['Total', 'Pendientes', 'Cerradas', 'Bloqueadas', 'Vencidas', 'Vencen periodo', 'Cerradas a tiempo', 'Cumplimiento'],
        [
            summary.get('total_tasks', 0),
            summary.get('pending', 0),
            summary.get('closed', 0),
            summary.get('blocked', 0),
            summary.get('overdue', 0),
            summary.get('due_in_period', 0),
            summary.get('closed_on_time', 0),
            f"{summary.get('compliance_rate')}%" if summary.get('compliance_rate') is not None else 'N/A',
        ],
    ]
    summary_table = Table(summary_data, hAlign='LEFT')
    summary_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#d1d5db')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.extend([summary_table, Spacer(1, 16)])
    elements.append(Paragraph('Cumplimiento: porcentaje de tareas cerradas dentro del plazo durante el periodo informado.', styles['BodyText']))
    elements.extend(_section_title('Distribucion por estado', styles))
    status_rows = [['Estado', 'Cantidad']] + [
        [_display_status(row.get('status') or row.get('status_id') or row.get('status', '-')), row.get('count', 0)]
        for row in payload.get('distributions', {}).get('by_status', [])
    ]
    status_table = Table(status_rows, hAlign='LEFT')
    status_table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#d1d5db')), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold')]))
    elements.append(status_table)
    elements.append(PageBreak())

    for title, key in [
        ('Tareas criticas', 'critical_tasks'),
        ('Tareas vencidas', 'overdue_tasks'),
        ('Tareas bloqueadas', 'blocked_tasks'),
        ('Trabajos cerrados', 'closed_tasks'),
        ('Pendientes del siguiente periodo', 'next_period_tasks'),
        ('Tareas incluidas en el informe', 'tasks'),
    ]:
        elements.extend(_section_title(title, styles))
        elements.extend(_task_table(payload.get(key, []), styles))

    elements.extend(_section_title('Evidencias', styles))
    elements.append(Paragraph('Las fotografias, documentos y comentarios de respaldo se encuentran disponibles en la ficha de cada tarea.', styles['BodyText']))
    elements.extend(_section_title('Observaciones', styles))
    elements.append(Paragraph('Este informe resume el estado de las tareas operacionales segun los criterios seleccionados al momento de su generacion.', styles['BodyText']))

    document.build(elements)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
