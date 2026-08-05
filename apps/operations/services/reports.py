from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.utils import timezone

from apps.operations.filters import operation_period_q
from apps.operations.models import OperationTaskStatus


def _distribution(queryset, field_name, label_field=None):
    values = queryset.values(field_name).annotate(count=Count('id')).order_by(field_name)
    if not label_field:
        return list(values)
    labels = {
        row[field_name]: row[label_field]
        for row in queryset.values(field_name, label_field).exclude(**{f'{field_name}__isnull': True})
    }
    return [{**row, 'label': labels.get(row[field_name], '')} for row in values]


def build_summary(queryset, *, start=None, end=None, include_costs=True):
    base_queryset = queryset
    if start or end:
        base_queryset = base_queryset.filter(operation_period_q(start=start, end=end)).distinct()

    now = timezone.now()
    due_in_period = base_queryset
    if start:
        due_in_period = due_in_period.filter(due_at__gte=start)
    if end:
        due_in_period = due_in_period.filter(due_at__lte=end)
    due_in_period = due_in_period.exclude(due_at__isnull=True)
    due_count = due_in_period.count()
    closed_on_time = due_in_period.filter(status=OperationTaskStatus.CLOSED, closed_at__lte=F('due_at')).count()
    close_duration = base_queryset.filter(status=OperationTaskStatus.CLOSED, closed_at__isnull=False).aggregate(
        average=Avg(ExpressionWrapper(F('closed_at') - F('detected_at'), output_field=DurationField()))
    )['average']
    pending_query = ~Q(status__in=[OperationTaskStatus.CLOSED, OperationTaskStatus.CANCELLED])
    pending_next_period = base_queryset.filter(pending_query, due_at__gt=end).count() if end else 0

    summary = {
        'total_tasks': base_queryset.count(),
        'detected': base_queryset.filter(status=OperationTaskStatus.DETECTED).count(),
        'assigned': base_queryset.filter(status=OperationTaskStatus.ASSIGNED).count(),
        'in_progress': base_queryset.filter(status=OperationTaskStatus.IN_PROGRESS).count(),
        'executed': base_queryset.filter(status=OperationTaskStatus.EXECUTED).count(),
        'in_verification': base_queryset.filter(status=OperationTaskStatus.VERIFICATION).count(),
        'closed': base_queryset.filter(status=OperationTaskStatus.CLOSED).count(),
        'blocked': base_queryset.filter(Q(status=OperationTaskStatus.BLOCKED) | Q(blocks__is_active=True)).distinct().count(),
        'cancelled': base_queryset.filter(status=OperationTaskStatus.CANCELLED).count(),
        'pending': base_queryset.filter(pending_query).count(),
        'overdue': base_queryset.filter(due_at__lt=now).exclude(status__in=[OperationTaskStatus.CLOSED, OperationTaskStatus.CANCELLED]).count(),
        'due_in_period': due_count,
        'closed_on_time': closed_on_time,
        'compliance_rate': round((closed_on_time / due_count) * 100, 2) if due_count else None,
        'average_close_hours': round(close_duration.total_seconds() / 3600, 2) if close_duration else None,
        'blocked_by_budget': base_queryset.filter(requires_budget=True, approval_status='PENDING').count(),
        'pending_next_period': pending_next_period,
    }
    if include_costs:
        cost_totals = base_queryset.aggregate(cost_estimated=Sum('cost_estimated'), cost_real=Sum('cost_real'))
        summary.update(cost_totals)
    return {
        'summary': summary,
        'distributions': {
            'by_status': _distribution(base_queryset, 'status'),
            'by_priority': _distribution(base_queryset, 'priority'),
            'by_area': _distribution(base_queryset, 'area_id', 'area__name'),
            'by_task_type': _distribution(base_queryset, 'task_type_id', 'task_type__name'),
            'by_sector': _distribution(base_queryset.exclude(sector=''), 'sector'),
            'by_geo_asset': list(
                base_queryset.exclude(geo_asset__isnull=True)
                .values('geo_asset_id', 'geo_asset__title')
                .annotate(count=Count('id'))
                .order_by('-count', 'geo_asset__title')[:20]
            ),
            'by_executor': list(
                base_queryset.exclude(executor__isnull=True)
                .values('executor_id', 'executor__name')
                .annotate(count=Count('id'))
                .order_by('-count', 'executor__name')[:20]
            ),
        },
    }


def _task_row(task):
    return {
        'id': task.id,
        'code': task.code,
        'title': task.title,
        'status': task.status,
        'priority': task.priority,
        'area': task.area.name if task.area_id else '',
        'task_type': task.task_type.name if task.task_type_id else '',
        'sector': task.sector,
        'geo_asset': task.geo_asset.title if task.geo_asset_id and task.geo_asset else '',
        'parcela': task.parcela.codigo_parcela if task.parcela_id and task.parcela else '',
        'executor': task.executor.name if task.executor_id and task.executor else (task.executor_user.full_name if task.executor_user_id and task.executor_user else task.executor_manual_label),
        'detected_at': task.detected_at,
        'due_at': task.due_at,
        'closed_at': task.closed_at,
    }


def build_report_payload(queryset, *, filters, start=None, end=None, include_costs=True, generated_by=None):
    queryset = queryset.order_by('-priority', '-detected_at', 'code')
    summary = build_summary(queryset, start=start, end=end, include_costs=include_costs)
    now = timezone.now()
    pending_query = ~Q(status__in=[OperationTaskStatus.CLOSED, OperationTaskStatus.CANCELLED])
    return {
        'filters': filters,
        'period': {
            'start': start.isoformat() if start else None,
            'end': end.isoformat() if end else None,
        },
        'generated_at': now.isoformat(),
        'generated_by': generated_by or '',
        'compliance_definition': 'tareas cerradas dentro del plazo / tareas cuyo vencimiento corresponde al periodo',
        **summary,
        'tasks': [_task_row(task) for task in queryset[:500]],
        'critical_tasks': [_task_row(task) for task in queryset.filter(priority='CRITICAL')[:50]],
        'overdue_tasks': [_task_row(task) for task in queryset.filter(pending_query, due_at__lt=now)[:50]],
        'blocked_tasks': [_task_row(task) for task in queryset.filter(Q(status=OperationTaskStatus.BLOCKED) | Q(blocks__is_active=True)).distinct()[:50]],
        'closed_tasks': [_task_row(task) for task in queryset.filter(status=OperationTaskStatus.CLOSED)[:100]],
        'next_period_tasks': [_task_row(task) for task in queryset.filter(pending_query, due_at__gt=end)[:100]] if end else [],
    }
