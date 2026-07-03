from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

from apps.access_control.models import AccessRecord
from apps.finance.models import (
    CommonExpenseDebt,
    FinancialMovement,
    FinancialMovementCategory,
    FinancialMovementType,
    PaymentAgreement,
    PaymentStatus,
    ServiceDebt,
    UnpaidFine,
)
from apps.maps_app.models import Objective, ObjectiveStatus, Visit
from apps.missions.models import DroneFlight
from apps.notes.models import AdministrativeNote
from apps.parcels.models import Parcel, ParcelStatus
from apps.people.models import ParcelResident
from apps.supervisor.models import NotificationFine, NotificationStatus
from apps.utilities.models import ServiceCut
from apps.vehicles.models import Vehicle

DEFAULT_PRESET = 'last_30_days'


@dataclass
class DateRange:
    preset: str
    date_from: date
    date_to: date
    previous_from: date
    previous_to: date

    @property
    def days(self) -> int:
        return (self.date_to - self.date_from).days + 1


def daterange(start: date, end: date):
    days = (end - start).days
    for offset in range(days + 1):
        yield start + timedelta(days=offset)


def safe_decimal(value) -> Decimal:
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def to_money(value: Decimal | int | float) -> float:
    return round(float(safe_decimal(value)), 2)


def to_number(value: Decimal | int | float) -> float:
    return round(float(safe_decimal(value)), 4)


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        if current == 0:
            return 0.0
        return 100.0
    return round(((current - previous) / previous) * 100, 2)


class DashboardAnalyticsService:
    payment_categories = {
        FinancialMovementCategory.PAYMENT_GC,
        FinancialMovementCategory.PAYMENT_SERVICE,
        FinancialMovementCategory.PAYMENT_AGREEMENT,
        FinancialMovementCategory.PAYMENT_FINE,
    }

    def __init__(
        self,
        *,
        date_range: DateRange,
        parcel_status: str | None = None,
        parcel_letter: str | None = None,
    ):
        self.date_range = date_range
        self.today = timezone.localdate()
        self.parcel_status = (parcel_status or '').strip().upper()
        self.parcel_letter = (parcel_letter or '').strip().upper()
        self.parcel_filters_active = bool(self.parcel_status or self.parcel_letter)

        self.parcels_qs = Parcel.objects.all()
        if self.parcel_status in {ParcelStatus.ACTIVA, ParcelStatus.INACTIVA, ParcelStatus.SUSPENDIDA}:
            self.parcels_qs = self.parcels_qs.filter(estado=self.parcel_status)
        if self.parcel_letter:
            self.parcels_qs = self.parcels_qs.filter(letra_lote__iexact=self.parcel_letter)

        self.parcel_ids = list(self.parcels_qs.values_list('id', flat=True))
        self._obligations_cache: list[dict] | None = None
        self._pending_by_parcel_cache: dict[int, Decimal] | None = None
        self._morose_series_cache: dict[tuple[date, date], list[dict]] = {}

    @classmethod
    def from_request(cls, request) -> 'DashboardAnalyticsService':
        date_range = cls._resolve_date_range(
            preset=request.query_params.get('preset', DEFAULT_PRESET),
            date_from_raw=request.query_params.get('date_from'),
            date_to_raw=request.query_params.get('date_to'),
        )
        return cls(
            date_range=date_range,
            parcel_status=request.query_params.get('parcel_status'),
            parcel_letter=request.query_params.get('parcel_letter'),
        )

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return None

    @classmethod
    def _resolve_date_range(cls, *, preset: str, date_from_raw: str | None, date_to_raw: str | None) -> DateRange:
        today = timezone.localdate()
        normalized = (preset or DEFAULT_PRESET).strip().lower()

        if normalized == 'today':
            date_from = today
            date_to = today
        elif normalized in {'last_7_days', '7d'}:
            date_from = today - timedelta(days=6)
            date_to = today
            normalized = 'last_7_days'
        elif normalized in {'last_30_days', '30d'}:
            date_from = today - timedelta(days=29)
            date_to = today
            normalized = 'last_30_days'
        elif normalized == 'this_month':
            date_from = today.replace(day=1)
            date_to = today
        elif normalized == 'custom':
            parsed_from = cls._parse_date(date_from_raw)
            parsed_to = cls._parse_date(date_to_raw)
            if parsed_from and parsed_to and parsed_from <= parsed_to:
                date_from = parsed_from
                date_to = parsed_to
            else:
                normalized = DEFAULT_PRESET
                date_from = today - timedelta(days=29)
                date_to = today
        else:
            normalized = DEFAULT_PRESET
            date_from = today - timedelta(days=29)
            date_to = today

        if date_to > today:
            date_to = today
        if date_from > date_to:
            date_from = date_to

        max_days = settings.DASHBOARD_MAX_RANGE_DAYS
        if (date_to - date_from).days + 1 > max_days:
            date_from = date_to - timedelta(days=max_days - 1)
            normalized = 'custom_limited' if normalized == 'custom' else normalized

        days = (date_to - date_from).days + 1
        previous_to = date_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=days - 1)

        return DateRange(
            preset=normalized,
            date_from=date_from,
            date_to=date_to,
            previous_from=previous_from,
            previous_to=previous_to,
        )

    def build(self) -> dict:
        kpis = self._build_kpis()
        charts = self._build_charts(kpis)
        smart = self._build_smart_indicators(kpis, charts)
        alerts, anomalies = self._build_alerts(kpis, smart, charts)
        insights = self._build_insights(kpis, smart, charts)
        rankings = self._build_rankings()

        return {
            'meta': {
                'preset': self.date_range.preset,
                'date_from': self.date_range.date_from.isoformat(),
                'date_to': self.date_range.date_to.isoformat(),
                'previous_from': self.date_range.previous_from.isoformat(),
                'previous_to': self.date_range.previous_to.isoformat(),
                'days': self.date_range.days,
                'filters': {'parcel_status': self.parcel_status or '', 'parcel_letter': self.parcel_letter or ''},
            },
            'kpis': kpis,
            'smart_indicators': smart,
            'alerts': alerts,
            'anomalies': anomalies,
            'insights': insights,
            'charts': charts,
            'rankings': rankings,
            # backward-compatible keys for the previous dashboard
            'parcelas_total': kpis['parcels_total'],
            'parcelas_criticas': kpis['parcels_in_arrears'],
            'deuda_gc_total': kpis['pending_gc_total'],
            'deuda_ays_total': kpis['pending_service_total'],
            'cortes_vigentes': kpis['active_cuts'],
        }

    def _apply_parcel_filter(self, qs, field_name: str = 'parcela'):
        if not self.parcel_filters_active:
            return qs
        if not self.parcel_ids:
            return qs.none()
        return qs.filter(**{f'{field_name}__in': self.parcel_ids})

    def _movements_queryset(self):
        return self._apply_parcel_filter(FinancialMovement.objects.filter(is_confirmed=True))

    def _income_queryset(self):
        return self._movements_queryset().filter(movement_type=FinancialMovementType.INCOME)

    def _expense_queryset(self):
        return self._movements_queryset().filter(movement_type=FinancialMovementType.EXPENSE)

    def _sum_qs(self, qs, field_name: str = 'amount') -> Decimal:
        return safe_decimal(qs.aggregate(total=Sum(field_name))['total'])

    def _pending_by_parcel(self) -> dict[int, Decimal]:
        if self._pending_by_parcel_cache is not None:
            return self._pending_by_parcel_cache

        pending_by_parcel: defaultdict[int, Decimal] = defaultdict(lambda: Decimal('0'))
        pending_statuses = [PaymentStatus.PENDIENTE, PaymentStatus.PARCIAL, PaymentStatus.VENCIDO]
        for model, amount_field in (
            (CommonExpenseDebt, 'total_pesos'),
            (ServiceDebt, 'saldo_total'),
            (PaymentAgreement, 'saldo_monto'),
            (UnpaidFine, 'saldo_monto'),
        ):
            rows = self._apply_parcel_filter(model.objects.filter(estado_pago__in=pending_statuses)).values('parcela_id').annotate(total=Sum(amount_field))
            for row in rows:
                pending_by_parcel[row['parcela_id']] += safe_decimal(row['total'])

        self._pending_by_parcel_cache = dict(pending_by_parcel)
        return self._pending_by_parcel_cache

    def _collect_obligations(self) -> list[dict]:
        if self._obligations_cache is not None:
            return self._obligations_cache

        obligations: list[dict] = []
        for model in (CommonExpenseDebt, ServiceDebt, PaymentAgreement, UnpaidFine):
            rows = self._apply_parcel_filter(model.objects.values('parcela_id', 'created_at', 'updated_at', 'estado_pago'))
            for row in rows:
                obligations.append(
                    {
                        'parcela_id': row['parcela_id'],
                        'start': row['created_at'].date(),
                        'end': row['updated_at'].date() if row['estado_pago'] == PaymentStatus.PAGADO else None,
                    }
                )
        self._obligations_cache = obligations
        return obligations

    def _morose_count_for_day(self, target_day: date) -> int:
        obligations = self._collect_obligations()
        active = {
            item['parcela_id']
            for item in obligations
            if item['start'] <= target_day and (item['end'] is None or item['end'] > target_day)
        }
        return len(active)

    def _morose_series(self, start: date, end: date) -> list[dict]:
        cache_key = (start, end)
        if cache_key in self._morose_series_cache:
            return self._morose_series_cache[cache_key]

        obligations = self._collect_obligations()
        filtered = [item for item in obligations if item['start'] <= end and (item['end'] is None or item['end'] > start)]
        series = []
        for day in daterange(start, end):
            active = {
                item['parcela_id']
                for item in filtered
                if item['start'] <= day and (item['end'] is None or item['end'] > day)
            }
            series.append({'date': day.isoformat(), 'count': len(active)})

        self._morose_series_cache[cache_key] = series
        return series

    def _build_kpis(self) -> dict:
        parcels_total = self.parcels_qs.count()
        parcels_active = self.parcels_qs.filter(estado=ParcelStatus.ACTIVA).count()

        pending_by_parcel = self._pending_by_parcel()
        parcels_in_arrears = len(pending_by_parcel)
        arrears_rate = to_number((Decimal(parcels_in_arrears) / Decimal(parcels_total) * Decimal('100')) if parcels_total else 0)

        residents_total = self._apply_parcel_filter(ParcelResident.objects.filter(is_active=True)).count()
        vehicles_total = self._apply_parcel_filter(Vehicle.objects.filter(activo=True)).count()
        visits_today = self._apply_parcel_filter(Visit.objects.filter(visit_datetime__date=self.today)).count()
        blocked_accesses = self._apply_parcel_filter(
            AccessRecord.objects.filter(status='blocked', access_datetime__date__range=(self.date_range.date_from, self.date_range.date_to))
        ).count()
        blocked_accesses_today = self._apply_parcel_filter(AccessRecord.objects.filter(status='blocked', access_datetime__date=self.today)).count()

        today_income_qs = self._income_queryset().filter(occurred_at__date=self.today)
        payments_today_qs = today_income_qs.filter(category__in=self.payment_categories)
        payments_today = payments_today_qs.count()

        month_start = self.today.replace(day=1)
        collected_today = self._sum_qs(today_income_qs)
        collected_month = self._sum_qs(self._income_queryset().filter(occurred_at__date__range=(month_start, self.today)))
        expense_today = self._sum_qs(self._expense_queryset().filter(occurred_at__date=self.today))

        pending_statuses = [PaymentStatus.PENDIENTE, PaymentStatus.PARCIAL, PaymentStatus.VENCIDO]
        pending_gc_total = self._sum_qs(self._apply_parcel_filter(CommonExpenseDebt.objects.filter(estado_pago__in=pending_statuses)), 'total_pesos')
        pending_service_total = self._sum_qs(self._apply_parcel_filter(ServiceDebt.objects.filter(estado_pago__in=pending_statuses)), 'saldo_total')
        pending_agreements_total = self._sum_qs(self._apply_parcel_filter(PaymentAgreement.objects.filter(estado_pago__in=pending_statuses)), 'saldo_monto')
        pending_fines_total = self._sum_qs(self._apply_parcel_filter(UnpaidFine.objects.filter(estado_pago__in=pending_statuses)), 'saldo_monto')
        pending_total = pending_gc_total + pending_service_total + pending_agreements_total + pending_fines_total

        active_cuts = self._apply_parcel_filter(ServiceCut.objects.filter(activo=True)).count()
        open_objectives = self._apply_parcel_filter(
            Objective.objects.filter(status__in=[ObjectiveStatus.PENDING, ObjectiveStatus.IN_PROGRESS, ObjectiveStatus.OVERDUE])
        ).count()
        open_notifications = self._apply_parcel_filter(NotificationFine.objects.filter(status=NotificationStatus.PENDING)).count()
        open_incidents = open_objectives + open_notifications

        return {
            'parcels_total': parcels_total,
            'parcels_active': parcels_active,
            'parcels_in_arrears': parcels_in_arrears,
            'arrears_rate': arrears_rate,
            'residents_total': residents_total,
            'vehicles_total': vehicles_total,
            'visits_today': visits_today,
            'blocked_accesses': blocked_accesses,
            'blocked_accesses_today': blocked_accesses_today,
            'payments_today': payments_today,
            'collected_today': to_money(collected_today),
            'collected_month': to_money(collected_month),
            'pending_total': to_money(pending_total),
            'pending_gc_total': to_money(pending_gc_total),
            'pending_service_total': to_money(pending_service_total),
            'pending_agreements_total': to_money(pending_agreements_total),
            'pending_fines_total': to_money(pending_fines_total),
            'open_incidents': open_incidents,
            'open_objectives': open_objectives,
            'open_notifications': open_notifications,
            'active_cuts': active_cuts,
            'income_today': to_money(collected_today),
            'expense_today': to_money(expense_today),
        }

    def _build_charts(self, kpis: dict) -> dict:
        date_from = self.date_range.date_from
        date_to = self.date_range.date_to
        days = self.date_range.days

        arrears_daily = self._morose_series(date_from, date_to)

        income_by_day = {
            row['day']: row
            for row in self._income_queryset()
            .filter(occurred_at__date__range=(date_from, date_to))
            .annotate(day=TruncDate('occurred_at'))
            .values('day')
            .annotate(amount=Sum('amount'), payments=Count('id'))
            .order_by('day')
        }
        collection_daily = []
        for day in daterange(date_from, date_to):
            row = income_by_day.get(day)
            collection_daily.append({'date': day.isoformat(), 'amount': to_money(row['amount']) if row else 0.0, 'payments': int(row['payments']) if row else 0})

        if days <= 45:
            resident_trunc = TruncDate('created_at')
            vehicle_trunc = TruncDate('created_at')
            label_key = 'date'
        elif days <= 180:
            resident_trunc = TruncWeek('created_at')
            vehicle_trunc = TruncWeek('created_at')
            label_key = 'week'
        else:
            resident_trunc = TruncMonth('created_at')
            vehicle_trunc = TruncMonth('created_at')
            label_key = 'month'

        residents_rows = (
            self._apply_parcel_filter(ParcelResident.objects.filter(created_at__date__range=(date_from, date_to)))
            .annotate(period=resident_trunc)
            .values('period')
            .annotate(total=Count('id'))
            .order_by('period')
        )
        new_residents_period = [{label_key: row['period'].date().isoformat() if hasattr(row['period'], 'date') else str(row['period']), 'count': row['total']} for row in residents_rows]

        vehicles_rows = (
            self._apply_parcel_filter(Vehicle.objects.filter(created_at__date__range=(date_from, date_to)))
            .annotate(period=vehicle_trunc)
            .values('period')
            .annotate(total=Count('id'))
            .order_by('period')
        )
        vehicles_registered_period = [{label_key: row['period'].date().isoformat() if hasattr(row['period'], 'date') else str(row['period']), 'count': row['total']} for row in vehicles_rows]

        parcels_status_comparison = [
            {'label': 'Al dia', 'value': max(kpis['parcels_total'] - kpis['parcels_in_arrears'], 0)},
            {'label': 'Morosas', 'value': kpis['parcels_in_arrears']},
        ]

        status_counter: Counter[str] = Counter()
        for model in (CommonExpenseDebt, ServiceDebt, PaymentAgreement, UnpaidFine):
            rows = self._apply_parcel_filter(model.objects).values('estado_pago').annotate(total=Count('id'))
            for row in rows:
                status_counter[row['estado_pago']] += row['total']
        payment_status_distribution = [{'label': status, 'value': value} for status, value in status_counter.items()]

        month_limit_start = (self.today.replace(day=1) - timedelta(days=330)).replace(day=1)
        monthly_collection_trend = [
            {'month': row['month'].date().strftime('%Y-%m'), 'amount': to_money(row['total'])}
            for row in self._income_queryset()
            .filter(occurred_at__date__range=(month_limit_start, self.today))
            .annotate(month=TruncMonth('occurred_at'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        ]

        pending_by_parcel = self._pending_by_parcel()
        parcel_codes = {row['id']: row['codigo_parcela'] for row in Parcel.objects.filter(id__in=list(pending_by_parcel.keys())).values('id', 'codigo_parcela')}
        top_parcels_debt = [
            {'parcel_id': parcel_id, 'parcel_code': parcel_codes.get(parcel_id, f'#{parcel_id}'), 'debt': to_money(amount)}
            for parcel_id, amount in sorted(pending_by_parcel.items(), key=lambda item: item[1], reverse=True)[:10]
        ]

        yearly_series = self._morose_series(self.today - timedelta(days=364), self.today)
        month_morosity: dict[str, int] = {}
        for item in yearly_series:
            month_label = item['date'][:7]
            month_morosity[month_label] = max(month_morosity.get(month_label, 0), item['count'])
        top_months_morosity = [{'month': month, 'count': count} for month, count in sorted(month_morosity.items(), key=lambda item: item[1], reverse=True)[:6]]

        return {
            'arrears_daily': arrears_daily,
            'collection_daily': collection_daily,
            'new_residents_period': new_residents_period,
            'vehicles_registered_period': vehicles_registered_period,
            'parcels_status_comparison': parcels_status_comparison,
            'payment_status_distribution': payment_status_distribution,
            'monthly_collection_trend': monthly_collection_trend,
            'top_parcels_debt': top_parcels_debt,
            'top_months_morosity': top_months_morosity,
            'operations_recent': self._build_recent_activity(),
        }

    def _build_recent_activity(self) -> list[dict]:
        events = []

        access_qs = self._apply_parcel_filter(AccessRecord.objects.select_related('parcela').order_by('-access_datetime'))
        for item in access_qs[:5]:
            events.append(
                {
                    'timestamp': item.access_datetime.isoformat(),
                    'type': 'acceso',
                    'title': item.full_name,
                    'detail': item.motive or 'Registro de acceso',
                    'severity': 'critical' if item.status == 'blocked' else 'info',
                }
            )
        visit_qs = self._apply_parcel_filter(Visit.objects.select_related('parcela').order_by('-visit_datetime'))
        for item in visit_qs[:5]:
            events.append(
                {
                    'timestamp': item.visit_datetime.isoformat(),
                    'type': 'visita',
                    'title': item.visitor_name,
                    'detail': item.purpose,
                    'severity': 'info',
                }
            )
        notes_qs = self._apply_parcel_filter(AdministrativeNote.objects.select_related('parcela').order_by('-created_at'))
        for item in notes_qs[:5]:
            events.append(
                {
                    'timestamp': item.created_at.isoformat(),
                    'type': 'anotacion',
                    'title': item.parcela.codigo_parcela,
                    'detail': (item.texto or '')[:120],
                    'severity': 'warning' if item.tipo in {'ALERTA', 'COBRANZA'} else 'info',
                }
            )
        movements_qs = self._apply_parcel_filter(FinancialMovement.objects.select_related('parcela').order_by('-occurred_at'))
        for item in movements_qs[:8]:
            events.append(
                {
                    'timestamp': item.occurred_at.isoformat(),
                    'type': 'finanza',
                    'title': item.get_movement_type_display(),
                    'detail': f'{item.get_category_display()} - ${to_money(item.amount):,.0f}',
                    'severity': 'success' if item.movement_type == FinancialMovementType.INCOME else 'warning',
                }
            )
        flights_qs = self._apply_parcel_filter(DroneFlight.objects.select_related('parcela').order_by('-flight_datetime'))
        for item in flights_qs[:5]:
            events.append(
                {
                    'timestamp': item.flight_datetime.isoformat(),
                    'type': 'vuelo',
                    'title': item.mission_code or 'Vuelo',
                    'detail': item.team_code or 'Equipo no informado',
                    'severity': 'info',
                }
            )

        events.sort(key=lambda row: row['timestamp'], reverse=True)
        return events[:12]

    def _build_smart_indicators(self, kpis: dict, charts: dict) -> dict:
        current_income_period = sum(item['amount'] for item in charts['collection_daily'])
        previous_income_period = to_money(
            self._sum_qs(self._income_queryset().filter(occurred_at__date__range=(self.date_range.previous_from, self.date_range.previous_to)))
        )
        collection_var_prev_period = pct_change(current_income_period, previous_income_period)

        current_morose = kpis['parcels_in_arrears']
        previous_morose = self._morose_count_for_day(self.date_range.previous_to)
        arrears_var_prev_period = pct_change(float(current_morose), float(previous_morose))

        yesterday = self.today - timedelta(days=1)
        collected_yesterday = to_money(self._sum_qs(self._income_queryset().filter(occurred_at__date=yesterday)))
        day_variation = pct_change(kpis['collected_today'], collected_yesterday)

        last_7_from = self.today - timedelta(days=6)
        prev_7_from = self.today - timedelta(days=13)
        prev_7_to = self.today - timedelta(days=7)
        collected_last_7 = to_money(self._sum_qs(self._income_queryset().filter(occurred_at__date__range=(last_7_from, self.today))))
        collected_prev_7 = to_money(self._sum_qs(self._income_queryset().filter(occurred_at__date__range=(prev_7_from, prev_7_to))))
        week_variation = pct_change(collected_last_7, collected_prev_7)

        month_start = self.today.replace(day=1)
        prev_month_last_day = month_start - timedelta(days=1)
        prev_month_start = prev_month_last_day.replace(day=1)
        current_month_income = to_money(self._sum_qs(self._income_queryset().filter(occurred_at__date__range=(month_start, self.today))))
        previous_month_income = to_money(self._sum_qs(self._income_queryset().filter(occurred_at__date__range=(prev_month_start, prev_month_last_day))))
        month_variation = pct_change(current_month_income, previous_month_income)

        payments_period = sum(item['payments'] for item in charts['collection_daily'])
        average_ticket = round(current_income_period / payments_period, 2) if payments_period else 0.0
        average_debt_per_morose = round(kpis['pending_total'] / current_morose, 2) if current_morose else 0.0
        residents_ratio = round(kpis['residents_total'] / kpis['parcels_total'], 3) if kpis['parcels_total'] else 0.0
        vehicles_ratio = round(kpis['vehicles_total'] / kpis['residents_total'], 3) if kpis['residents_total'] else 0.0

        days_in_month = calendar.monthrange(self.today.year, self.today.month)[1]
        elapsed_days = self.today.day
        projected_month_collection = round((kpis['collected_month'] / elapsed_days) * days_in_month, 2) if elapsed_days else 0.0

        health = 'green'
        if kpis['arrears_rate'] >= 30 or week_variation <= -20:
            health = 'red'
        elif kpis['arrears_rate'] >= 18 or week_variation <= -8:
            health = 'yellow'

        return {
            'arrears_variation_prev_period_pct': arrears_var_prev_period,
            'collection_variation_prev_period_pct': collection_var_prev_period,
            'collection_variation_day_pct': day_variation,
            'collection_variation_week_pct': week_variation,
            'collection_variation_month_pct': month_variation,
            'average_payment_ticket': average_ticket,
            'average_debt_per_morose_parcel': average_debt_per_morose,
            'residents_per_parcel_ratio': residents_ratio,
            'vehicles_per_resident_ratio': vehicles_ratio,
            'projected_month_collection': projected_month_collection,
            'health_semaphore': health,
        }

    def _build_alerts(self, kpis: dict, smart: dict, charts: dict) -> tuple[list[dict], list[dict]]:
        alerts: list[dict] = []
        anomalies: list[dict] = []

        if kpis['arrears_rate'] >= 30:
            alerts.append({'level': 'critical', 'title': 'Morosidad crítica', 'message': f"La morosidad alcanza {kpis['arrears_rate']:.1f}%."})
        elif kpis['arrears_rate'] >= 18:
            alerts.append({'level': 'warning', 'title': 'Morosidad en atención', 'message': f"Morosidad en {kpis['arrears_rate']:.1f}%."})

        if smart['collection_variation_week_pct'] <= -15:
            alerts.append(
                {
                    'level': 'warning',
                    'title': 'Caída de recaudación semanal',
                    'message': f"La recaudación semanal bajó {abs(smart['collection_variation_week_pct']):.1f}% vs semana anterior.",
                }
            )

        if kpis['expense_today'] > 0 and kpis['income_today'] > 0 and (kpis['expense_today'] / kpis['income_today']) >= 0.8:
            alerts.append({'level': 'warning', 'title': 'Gasto diario elevado', 'message': 'Los egresos de hoy superan el 80% de los ingresos.'})

        past_week = charts['collection_daily'][-8:-1] if len(charts['collection_daily']) > 7 else charts['collection_daily'][:-1]
        week_avg = sum(item['amount'] for item in past_week) / len(past_week) if past_week else 0.0
        if week_avg > 0 and kpis['collected_today'] < (week_avg * 0.5):
            anomalies.append({'type': 'collection_drop', 'severity': 'high', 'description': 'Caída brusca de pagos respecto al promedio semanal.'})
        if smart['arrears_variation_prev_period_pct'] >= 15:
            anomalies.append({'type': 'arrears_spike', 'severity': 'high', 'description': 'Aumento anormal de morosidad.'})

        residents_today = self._apply_parcel_filter(ParcelResident.objects.filter(created_at__date=self.today)).count()
        vehicles_today = self._apply_parcel_filter(Vehicle.objects.filter(created_at__date=self.today)).count()
        residents_2w = self._apply_parcel_filter(ParcelResident.objects.filter(created_at__date__range=(self.today - timedelta(days=14), self.today - timedelta(days=1)))).count()
        vehicles_2w = self._apply_parcel_filter(Vehicle.objects.filter(created_at__date__range=(self.today - timedelta(days=14), self.today - timedelta(days=1)))).count()
        residents_avg = residents_2w / 14 if residents_2w else 0
        vehicles_avg = vehicles_2w / 14 if vehicles_2w else 0
        if residents_avg > 0 and residents_today >= residents_avg * 2.2 and residents_today >= 3:
            anomalies.append({'type': 'resident_outlier', 'severity': 'medium', 'description': 'Registros de residentes fuera de patrón diario.'})
        if vehicles_avg > 0 and vehicles_today >= vehicles_avg * 2.2 and vehicles_today >= 3:
            anomalies.append({'type': 'vehicle_outlier', 'severity': 'medium', 'description': 'Registros de vehículos fuera de patrón diario.'})

        return alerts, anomalies

    def _build_insights(self, kpis: dict, smart: dict, charts: dict) -> list[str]:
        insights: list[str] = []
        insights.append(f"La morosidad actual es {kpis['arrears_rate']:.1f}% con {kpis['parcels_in_arrears']} parcelas comprometidas.")
        if smart['arrears_variation_prev_period_pct'] != 0:
            direction = 'subió' if smart['arrears_variation_prev_period_pct'] > 0 else 'bajó'
            insights.append(f"La morosidad {direction} {abs(smart['arrears_variation_prev_period_pct']):.1f}% respecto al periodo anterior.")
        if smart['collection_variation_day_pct'] != 0:
            direction = 'sobre' if smart['collection_variation_day_pct'] > 0 else 'bajo'
            insights.append(f"La recaudación de hoy está {abs(smart['collection_variation_day_pct']):.1f}% {direction} ayer.")

        top_parcels = charts.get('top_parcels_debt', [])[:3]
        if top_parcels and kpis['pending_total'] > 0:
            top_sum = sum(item['debt'] for item in top_parcels)
            concentration = (top_sum / kpis['pending_total']) * 100
            insights.append(f"{len(top_parcels)} parcelas concentran el {concentration:.1f}% de la deuda total.")

        month_collection = charts.get('monthly_collection_trend', [])
        if len(month_collection) >= 2:
            change = pct_change(month_collection[-1]['amount'], month_collection[-2]['amount'])
            direction = 'creció' if change >= 0 else 'cayó'
            insights.append(f"La recaudación mensual {direction} {abs(change):.1f}% frente al mes previo.")

        payment_days_rows = (
            self._income_queryset()
            .filter(occurred_at__date__range=(self.today - timedelta(days=180), self.today))
            .annotate(day=TruncDate('occurred_at'))
            .values('day')
            .annotate(total=Count('id'))
        )
        first_five = sum(row['total'] for row in payment_days_rows if row['day'].day <= 5)
        rest_days = sum(row['total'] for row in payment_days_rows if row['day'].day > 5)
        if first_five + rest_days > 0:
            ratio = (first_five / (first_five + rest_days)) * 100
            insights.append(f"El {ratio:.1f}% de los pagos ocurre en los primeros 5 días del mes.")

        insights.append(f"Ticket promedio de pago del periodo: ${smart['average_payment_ticket']:,.0f}.")
        insights.append(f"Proyección simple de recaudación mensual: ${smart['projected_month_collection']:,.0f}.")
        return insights[:8]

    def _build_rankings(self) -> dict:
        pending_by_parcel = self._pending_by_parcel()
        cut_counts = {row['parcela_id']: row['total'] for row in self._apply_parcel_filter(ServiceCut.objects.filter(activo=True)).values('parcela_id').annotate(total=Count('id'))}
        objective_counts = {
            row['parcela_id']: row['total']
            for row in self._apply_parcel_filter(Objective.objects.filter(status__in=[ObjectiveStatus.PENDING, ObjectiveStatus.IN_PROGRESS, ObjectiveStatus.OVERDUE]))
            .values('parcela_id')
            .annotate(total=Count('id'))
        }

        involved_ids = set(pending_by_parcel.keys()) | set(cut_counts.keys()) | set(objective_counts.keys())
        parcel_codes = {row['id']: row['codigo_parcela'] for row in Parcel.objects.filter(id__in=list(involved_ids)).values('id', 'codigo_parcela')}
        avg_debt = to_number(sum(pending_by_parcel.values()) / Decimal(len(pending_by_parcel))) if pending_by_parcel else 0.0

        critical = []
        for parcel_id in involved_ids:
            debt = to_money(pending_by_parcel.get(parcel_id, Decimal('0')))
            cuts = cut_counts.get(parcel_id, 0)
            objectives = objective_counts.get(parcel_id, 0)
            debt_score = (debt / avg_debt) if avg_debt else (1.0 if debt > 0 else 0.0)
            score = round((debt_score * 2.5) + (cuts * 2.2) + (objectives * 1.5), 2)
            semaphore = 'green'
            if score >= 7:
                semaphore = 'red'
            elif score >= 3.5:
                semaphore = 'yellow'
            critical.append(
                {
                    'parcel_id': parcel_id,
                    'parcel_code': parcel_codes.get(parcel_id, f'#{parcel_id}'),
                    'pending_debt': debt,
                    'active_cuts': cuts,
                    'open_objectives': objectives,
                    'critical_score': score,
                    'semaphore': semaphore,
                }
            )

        critical.sort(key=lambda row: row['critical_score'], reverse=True)
        return {'critical_parcels': critical[:12]}
