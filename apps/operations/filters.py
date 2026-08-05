from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django_filters import rest_framework as filters
from rest_framework import exceptions

from apps.geo_operations.services.geometry import parse_bbox
from apps.operations.models import OperationTask, OperationTaskStatus


def _csv_values(value):
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        raw_values = value
    else:
        raw_values = str(value).split(',')
    return [str(item).strip() for item in raw_values if str(item).strip()]


def _parse_boundary(value, *, end=False):
    if not value:
        return None
    parsed_datetime = parse_datetime(str(value))
    if parsed_datetime:
        if timezone.is_naive(parsed_datetime):
            parsed_datetime = timezone.make_aware(parsed_datetime)
        return parsed_datetime
    parsed_date = parse_date(str(value))
    if not parsed_date:
        return None
    boundary_time = time.max if end else time.min
    return timezone.make_aware(datetime.combine(parsed_date, boundary_time))


def operation_period_q(start=None, end=None):
    query = Q()
    fields = ('detected_at', 'updated_at', 'closed_at')
    for field in fields:
        field_query = Q()
        if start:
            field_query &= Q(**{f'{field}__gte': start})
        if end:
            field_query &= Q(**{f'{field}__lte': end})
        if field_query:
            query |= field_query
    return query


class OperationTaskFilter(filters.FilterSet):
    status = filters.CharFilter(method='filter_csv')
    priority = filters.CharFilter(method='filter_csv')
    area = filters.NumberFilter(field_name='area_id')
    task_type = filters.NumberFilter(field_name='task_type_id')
    sector = filters.CharFilter(method='filter_csv')
    parcela = filters.NumberFilter(field_name='parcela_id')
    geo_asset = filters.NumberFilter(field_name='geo_asset_id')
    executor = filters.NumberFilter(field_name='executor_id')
    executor_user = filters.NumberFilter(field_name='executor_user_id')
    registered_by = filters.NumberFilter(field_name='registered_by_id')
    verified_by = filters.NumberFilter(field_name='verified_by_id')
    created_by = filters.NumberFilter(field_name='created_by_id')
    project = filters.NumberFilter(field_name='project_id')
    blocked = filters.BooleanFilter(method='filter_blocked')
    overdue = filters.BooleanFilter(method='filter_overdue')
    budget_pending = filters.BooleanFilter(method='filter_budget_pending')
    bbox = filters.CharFilter(method='filter_bbox')

    detected_from = filters.CharFilter(method='filter_detected_from')
    detected_to = filters.CharFilter(method='filter_detected_to')
    created_from = filters.CharFilter(method='filter_created_from')
    created_to = filters.CharFilter(method='filter_created_to')
    closed_from = filters.CharFilter(method='filter_closed_from')
    closed_to = filters.CharFilter(method='filter_closed_to')

    date_from = filters.CharFilter(method='noop')
    date_to = filters.CharFilter(method='noop')
    month = filters.CharFilter(method='noop')
    year = filters.CharFilter(method='noop')

    class Meta:
        model = OperationTask
        fields = [
            'status',
            'priority',
            'area',
            'task_type',
            'sector',
            'parcela',
            'geo_asset',
            'executor',
            'executor_user',
            'registered_by',
            'verified_by',
            'created_by',
            'project',
            'blocked',
            'overdue',
            'budget_pending',
            'bbox',
        ]

    def noop(self, queryset, name, value):
        return queryset

    def filter_csv(self, queryset, name, value):
        values = _csv_values(value)
        if not values:
            return queryset
        return queryset.filter(**{f'{name}__in': values})

    def filter_blocked(self, queryset, name, value):
        if value:
            return queryset.filter(Q(status=OperationTaskStatus.BLOCKED) | Q(blocks__is_active=True)).distinct()
        return queryset.exclude(Q(status=OperationTaskStatus.BLOCKED) | Q(blocks__is_active=True)).distinct()

    def filter_overdue(self, queryset, name, value):
        overdue_query = Q(due_at__lt=timezone.now()) & ~Q(status__in=[OperationTaskStatus.CLOSED, OperationTaskStatus.CANCELLED])
        return queryset.filter(overdue_query) if value else queryset.exclude(overdue_query)

    def filter_budget_pending(self, queryset, name, value):
        query = Q(requires_budget=True, approval_status='PENDING')
        return queryset.filter(query) if value else queryset.exclude(query)

    def filter_bbox(self, queryset, name, value):
        try:
            west, south, east, north = parse_bbox(value)
        except Exception as exc:
            raise exceptions.ValidationError({'bbox': 'bbox debe tener formato west,south,east,north.'}) from exc
        task_query = Q(max_lng__gte=west, min_lng__lte=east, max_lat__gte=south, min_lat__lte=north)
        asset_query = Q(
            geo_asset__max_lng__gte=west,
            geo_asset__min_lng__lte=east,
            geo_asset__max_lat__gte=south,
            geo_asset__min_lat__lte=north,
        )
        return queryset.filter(task_query | asset_query).distinct()

    def filter_detected_from(self, queryset, name, value):
        boundary = _parse_boundary(value)
        return queryset.filter(detected_at__gte=boundary) if boundary else queryset

    def filter_detected_to(self, queryset, name, value):
        boundary = _parse_boundary(value, end=True)
        return queryset.filter(detected_at__lte=boundary) if boundary else queryset

    def filter_created_from(self, queryset, name, value):
        boundary = _parse_boundary(value)
        return queryset.filter(created_at__gte=boundary) if boundary else queryset

    def filter_created_to(self, queryset, name, value):
        boundary = _parse_boundary(value, end=True)
        return queryset.filter(created_at__lte=boundary) if boundary else queryset

    def filter_closed_from(self, queryset, name, value):
        boundary = _parse_boundary(value)
        return queryset.filter(closed_at__gte=boundary) if boundary else queryset

    def filter_closed_to(self, queryset, name, value):
        boundary = _parse_boundary(value, end=True)
        return queryset.filter(closed_at__lte=boundary) if boundary else queryset

    def _period_bounds(self):
        params = self.data
        start = None
        end = None
        raw_month = params.get('month')
        raw_year = params.get('year')

        if raw_month:
            month_text = str(raw_month)
            if '-' in month_text:
                first_day = parse_date(f'{month_text}-01')
            elif raw_year:
                first_day = parse_date(f'{raw_year}-{int(month_text):02d}-01')
            else:
                first_day = None
            if first_day:
                start = timezone.make_aware(datetime.combine(first_day, time.min))
                if first_day.month == 12:
                    next_month = date(first_day.year + 1, 1, 1)
                else:
                    next_month = date(first_day.year, first_day.month + 1, 1)
                end = timezone.make_aware(datetime.combine(next_month, time.min)) - timedelta(microseconds=1)
        elif raw_year:
            first_day = parse_date(f'{raw_year}-01-01')
            if first_day:
                start = timezone.make_aware(datetime.combine(first_day, time.min))
                end = timezone.make_aware(datetime.combine(date(first_day.year + 1, 1, 1), time.min)) - timedelta(microseconds=1)

        explicit_start = _parse_boundary(params.get('date_from'))
        explicit_end = _parse_boundary(params.get('date_to'), end=True)
        return explicit_start or start, explicit_end or end

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        start, end = self._period_bounds()
        if start or end:
            queryset = queryset.filter(operation_period_q(start=start, end=end)).distinct()
        return queryset
