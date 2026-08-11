from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q, Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserActorType, UserRole
from apps.core.cache_utils import request_cache_key
from apps.core.permissions import RoleBasedActionPermission
from apps.core.viewsets import CachedModelViewSet
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
from apps.finance.serializers import (
    CommonExpenseDebtSerializer,
    FinancialMovementSerializer,
    PaymentAgreementSerializer,
    ServiceDebtSerializer,
    UnpaidFineSerializer,
)
from apps.parcels.models import Parcel
from apps.people.models import OwnershipType, ParcelOwnership

PENDING_STATUSES = [PaymentStatus.PENDIENTE, PaymentStatus.PARCIAL, PaymentStatus.VENCIDO]
ACTIVE_AGREEMENT_STATUSES = [PaymentStatus.PENDIENTE, PaymentStatus.PARCIAL]
BLOCKED_ACTOR_TYPES = [UserActorType.CENTRAL_MONITOREO, UserActorType.PORTAL_ACCESO, UserActorType.OPERADOR_DRONE]
PAYMENT_CATEGORIES = {
    FinancialMovementCategory.PAYMENT_GC,
    FinancialMovementCategory.PAYMENT_SERVICE,
    FinancialMovementCategory.PAYMENT_AGREEMENT,
    FinancialMovementCategory.PAYMENT_FINE,
}


def _safe_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_money(value) -> float:
    return round(float(_safe_decimal(value)), 2)


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _has_finance_access(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True

    role_level = {
        UserRole.CONSULTA: 10,
        UserRole.OPERADOR: 20,
        UserRole.ADMINISTRADOR: 30,
        UserRole.SUPERADMIN: 40,
    }
    if role_level.get(getattr(user, "role", ""), 0) < role_level[UserRole.CONSULTA]:
        return False
    return getattr(user, "actor_type", "") not in BLOCKED_ACTOR_TYPES


def _apply_period_filter(queryset, *, date_field: str, date_from=None, date_to=None, datetime_field=False):
    if not date_from and not date_to:
        return queryset

    if datetime_field:
        if date_from and date_to:
            return queryset.filter(**{f"{date_field}__date__range": (date_from, date_to)})
        if date_from:
            return queryset.filter(**{f"{date_field}__date__gte": date_from})
        return queryset.filter(**{f"{date_field}__date__lte": date_to})

    period_filters = Q()
    if date_from and date_to:
        period_filters = Q(**{f"{date_field}__range": (date_from, date_to)}) | Q(
            **{f"{date_field}__isnull": True, "created_at__date__range": (date_from, date_to)}
        )
    elif date_from:
        period_filters = Q(**{f"{date_field}__gte": date_from}) | Q(**{f"{date_field}__isnull": True, "created_at__date__gte": date_from})
    elif date_to:
        period_filters = Q(**{f"{date_field}__lte": date_to}) | Q(**{f"{date_field}__isnull": True, "created_at__date__lte": date_to})
    return queryset.filter(period_filters)


class FinanceSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _has_finance_access(request.user):
            return Response({"detail": "No autorizado"}, status=403)

        parcel_id = request.query_params.get("parcel")
        date_from = _parse_date(request.query_params.get("date_from"))
        date_to = _parse_date(request.query_params.get("date_to"))
        cache_timeout = settings.FINANCE_SUMMARY_CACHE_SECONDS
        cache_key = request_cache_key("finance:summary", request)
        if cache_timeout:
            cached_payload = cache.get(cache_key)
            if cached_payload is not None:
                return Response(cached_payload)

        debt_filters = {}
        movement_filters = {}
        if parcel_id:
            debt_filters["parcela_id"] = parcel_id
            movement_filters["parcela_id"] = parcel_id

        gc_qs = _apply_period_filter(
            CommonExpenseDebt.objects.filter(**debt_filters, estado_pago__in=PENDING_STATUSES),
            date_field="fecha_corte",
            date_from=date_from,
            date_to=date_to,
        )
        service_qs = _apply_period_filter(
            ServiceDebt.objects.filter(**debt_filters, estado_pago__in=PENDING_STATUSES),
            date_field="created_at",
            date_from=date_from,
            date_to=date_to,
            datetime_field=True,
        )
        agreements_qs = _apply_period_filter(
            PaymentAgreement.objects.filter(**debt_filters, estado_pago__in=PENDING_STATUSES),
            date_field="fecha_emision",
            date_from=date_from,
            date_to=date_to,
        )
        fines_qs = _apply_period_filter(
            UnpaidFine.objects.filter(**debt_filters, estado_pago__in=PENDING_STATUSES),
            date_field="fecha_emision",
            date_from=date_from,
            date_to=date_to,
        )

        gc_total = _safe_decimal(gc_qs.aggregate(total=Sum("total_pesos"))["total"])
        service_total = _safe_decimal(service_qs.aggregate(total=Sum("saldo_total"))["total"])
        agreements_total = _safe_decimal(agreements_qs.aggregate(total=Sum("saldo_monto"))["total"])
        fines_total = _safe_decimal(fines_qs.aggregate(total=Sum("saldo_monto"))["total"])
        debt_total = gc_total + service_total + agreements_total + fines_total

        debt_overdue_total = (
            _safe_decimal(gc_qs.filter(estado_pago=PaymentStatus.VENCIDO).aggregate(total=Sum("total_pesos"))["total"])
            + _safe_decimal(service_qs.filter(estado_pago=PaymentStatus.VENCIDO).aggregate(total=Sum("saldo_total"))["total"])
            + _safe_decimal(agreements_qs.filter(estado_pago=PaymentStatus.VENCIDO).aggregate(total=Sum("saldo_monto"))["total"])
            + _safe_decimal(fines_qs.filter(estado_pago=PaymentStatus.VENCIDO).aggregate(total=Sum("saldo_monto"))["total"])
        )

        today = timezone.localdate()
        month_start = today.replace(day=1)
        movements_month_qs = FinancialMovement.objects.filter(
            **movement_filters,
            is_confirmed=True,
            movement_type=FinancialMovementType.INCOME,
            category__in=PAYMENT_CATEGORIES,
            occurred_at__date__range=(month_start, today),
        )
        payments_month_amount = _safe_decimal(movements_month_qs.aggregate(total=Sum("amount"))["total"])
        payments_month_count = movements_month_qs.count()

        agreements_active_count = PaymentAgreement.objects.filter(
            **debt_filters, estado_pago__in=ACTIVE_AGREEMENT_STATUSES
        ).count()
        fines_pending_count = UnpaidFine.objects.filter(**debt_filters, estado_pago__in=PENDING_STATUSES).count()

        last_12_start = (today.replace(day=1) - timedelta(days=330)).replace(day=1)
        monthly_movement_rows = (
            FinancialMovement.objects.filter(
                **movement_filters,
                is_confirmed=True,
                occurred_at__date__range=(last_12_start, today),
            )
            .annotate(month=TruncMonth("occurred_at"))
            .values("month", "movement_type")
            .annotate(total=Sum("amount"))
            .order_by("month")
        )
        trend_bucket = defaultdict(lambda: {"payments": Decimal("0"), "expenses": Decimal("0")})
        for row in monthly_movement_rows:
            month_key = row["month"].date().strftime("%Y-%m")
            if row["movement_type"] == FinancialMovementType.INCOME:
                trend_bucket[month_key]["payments"] += _safe_decimal(row["total"])
            else:
                trend_bucket[month_key]["expenses"] += _safe_decimal(row["total"])

        monthly_trend = [
            {
                "month": month,
                "payments": _to_money(values["payments"]),
                "expenses": _to_money(values["expenses"]),
                "net": _to_money(values["payments"] - values["expenses"]),
            }
            for month, values in sorted(trend_bucket.items(), key=lambda item: item[0])
        ]

        debt_distribution = [
            {"label": "Gastos comunes", "value": _to_money(gc_total)},
            {"label": "Servicios", "value": _to_money(service_total)},
            {"label": "Convenios", "value": _to_money(agreements_total)},
            {"label": "Multas", "value": _to_money(fines_total)},
        ]

        payload = {
            "kpis": {
                "debt_total": _to_money(debt_total),
                "debt_overdue_total": _to_money(debt_overdue_total),
                "payments_month_amount": _to_money(payments_month_amount),
                "payments_month_count": payments_month_count,
                "agreements_active_count": agreements_active_count,
                "fines_pending_count": fines_pending_count,
            },
            "charts": {
                "monthly_trend": monthly_trend,
                "debt_distribution": debt_distribution,
            },
        }
        if cache_timeout:
            cache.set(cache_key, payload, timeout=cache_timeout)
        return Response(payload)


class FinanceConsolidatedPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


class FinanceConsolidatedView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = FinanceConsolidatedPagination

    def get(self, request):
        if not _has_finance_access(request.user):
            return Response({"detail": "No autorizado"}, status=403)

        cache_timeout = settings.FINANCE_CONSOLIDATED_CACHE_SECONDS
        cache_key = request_cache_key("finance:consolidated", request)
        if cache_timeout:
            cached_payload = cache.get(cache_key)
            if cached_payload is not None:
                return Response(cached_payload)

        search = (request.query_params.get("search") or "").strip()
        parcel_filter = (request.query_params.get("parcel") or "").strip()
        status_filter = (request.query_params.get("status") or "").strip().upper()
        ordering = (request.query_params.get("ordering") or "-total_debt").strip()
        date_from = _parse_date(request.query_params.get("date_from"))
        date_to = _parse_date(request.query_params.get("date_to"))

        parcel_qs = Parcel.objects.all()
        if parcel_filter:
            if str(parcel_filter).isdigit():
                parcel_qs = parcel_qs.filter(id=int(parcel_filter))
            else:
                parcel_qs = parcel_qs.filter(codigo_parcela__icontains=parcel_filter)
        if search:
            parcel_qs = parcel_qs.filter(
                Q(codigo_parcela__icontains=search)
                | Q(referencia_direccion__icontains=search)
                | Q(ownerships__persona__nombre_completo__icontains=search)
                | Q(ownerships__persona__rut__icontains=search)
            ).distinct()

        parcel_ids = list(parcel_qs.values_list("id", flat=True))
        if not parcel_ids:
            payload = {"count": 0, "next": None, "previous": None, "results": []}
            if cache_timeout:
                cache.set(cache_key, payload, timeout=cache_timeout)
            return Response(payload)

        principal_owner_rows = (
            ParcelOwnership.objects.select_related("persona")
            .filter(parcela_id__in=parcel_ids, tipo=OwnershipType.PRINCIPAL, is_active=True, is_deleted=False)
            .order_by("parcela_id", "id")
        )
        principal_owner_map = {}
        for ownership in principal_owner_rows:
            if ownership.parcela_id not in principal_owner_map:
                principal_owner_map[ownership.parcela_id] = ownership.persona

        rows_by_parcel = {
            parcel.id: {
                "parcel_id": parcel.id,
                "parcel_code": parcel.codigo_parcela,
                "parcel_status": parcel.estado,
                "owner_name": "",
                "owner_rut": "",
                "gc_debt": Decimal("0"),
                "services_debt": Decimal("0"),
                "agreements_debt": Decimal("0"),
                "fines_debt": Decimal("0"),
                "total_debt": Decimal("0"),
                "overdue_debt": Decimal("0"),
                "agreements_active_count": 0,
                "fines_pending_count": 0,
                "payments_period": Decimal("0"),
                "status": "AL_DIA",
            }
            for parcel in parcel_qs
        }

        for parcel_id, person in principal_owner_map.items():
            if person and parcel_id in rows_by_parcel:
                rows_by_parcel[parcel_id]["owner_name"] = person.nombre_completo or ""
                rows_by_parcel[parcel_id]["owner_rut"] = person.rut or ""

        model_specs = [
            (CommonExpenseDebt, "total_pesos", "gc_debt", "fecha_corte", False),
            (ServiceDebt, "saldo_total", "services_debt", "created_at", True),
            (PaymentAgreement, "saldo_monto", "agreements_debt", "fecha_emision", False),
            (UnpaidFine, "saldo_monto", "fines_debt", "fecha_emision", False),
        ]
        for model, amount_field, row_field, date_field, is_datetime in model_specs:
            debt_qs = _apply_period_filter(
                model.objects.filter(parcela_id__in=parcel_ids, estado_pago__in=PENDING_STATUSES),
                date_field=date_field,
                date_from=date_from,
                date_to=date_to,
                datetime_field=is_datetime,
            )
            for item in debt_qs.values("parcela_id", "estado_pago").annotate(total=Sum(amount_field), count=Count("id")):
                parcel_id = item["parcela_id"]
                amount = _safe_decimal(item["total"])
                if parcel_id not in rows_by_parcel:
                    continue

                rows_by_parcel[parcel_id][row_field] += amount
                rows_by_parcel[parcel_id]["total_debt"] += amount
                if item["estado_pago"] == PaymentStatus.VENCIDO:
                    rows_by_parcel[parcel_id]["overdue_debt"] += amount
                if model is PaymentAgreement and item["estado_pago"] in ACTIVE_AGREEMENT_STATUSES:
                    rows_by_parcel[parcel_id]["agreements_active_count"] += item["count"]
                if model is UnpaidFine:
                    rows_by_parcel[parcel_id]["fines_pending_count"] += item["count"]

        period_from = date_from or timezone.localdate().replace(day=1)
        period_to = date_to or timezone.localdate()
        payments_rows = (
            FinancialMovement.objects.filter(
                parcela_id__in=parcel_ids,
                is_confirmed=True,
                movement_type=FinancialMovementType.INCOME,
                category__in=PAYMENT_CATEGORIES,
                occurred_at__date__range=(period_from, period_to),
            )
            .values("parcela_id")
            .annotate(total=Sum("amount"))
        )
        for item in payments_rows:
            if item["parcela_id"] in rows_by_parcel:
                rows_by_parcel[item["parcela_id"]]["payments_period"] = _safe_decimal(item["total"])

        rows = []
        for row in rows_by_parcel.values():
            if row["overdue_debt"] > 0:
                row["status"] = "VENCIDA"
            elif row["total_debt"] > 0:
                row["status"] = "CON_DEUDA"
            else:
                row["status"] = "AL_DIA"

            if status_filter and row["status"] != status_filter:
                continue

            row["gc_debt"] = _to_money(row["gc_debt"])
            row["services_debt"] = _to_money(row["services_debt"])
            row["agreements_debt"] = _to_money(row["agreements_debt"])
            row["fines_debt"] = _to_money(row["fines_debt"])
            row["total_debt"] = _to_money(row["total_debt"])
            row["overdue_debt"] = _to_money(row["overdue_debt"])
            row["payments_period"] = _to_money(row["payments_period"])
            rows.append(row)

        valid_orderings = {
            "parcel_code": lambda item: item["parcel_code"],
            "-parcel_code": lambda item: item["parcel_code"],
            "total_debt": lambda item: item["total_debt"],
            "-total_debt": lambda item: item["total_debt"],
            "overdue_debt": lambda item: item["overdue_debt"],
            "-overdue_debt": lambda item: item["overdue_debt"],
            "payments_period": lambda item: item["payments_period"],
            "-payments_period": lambda item: item["payments_period"],
        }
        selected_ordering = ordering if ordering in valid_orderings else "-total_debt"
        rows.sort(key=valid_orderings[selected_ordering], reverse=selected_ordering.startswith("-"))

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(rows, request, view=self)
        payload = {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": page,
        }
        if cache_timeout:
            cache.set(cache_key, payload, timeout=cache_timeout)
        return Response(payload)


class CommonExpenseDebtViewSet(CachedModelViewSet):
    queryset = CommonExpenseDebt.objects.select_related("parcela", "persona").all()
    serializer_class = CommonExpenseDebtSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ["parcela__codigo_parcela"]
    filterset_fields = ["parcela", "estado_pago"]
    ordering_fields = ["created_at", "fecha_corte", "total_pesos"]
    required_roles_per_action = {
        "list": UserRole.CONSULTA,
        "retrieve": UserRole.CONSULTA,
        "create": UserRole.OPERADOR,
        "update": UserRole.OPERADOR,
        "partial_update": UserRole.OPERADOR,
        "destroy": UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {"*": BLOCKED_ACTOR_TYPES}


class ServiceDebtViewSet(CachedModelViewSet):
    queryset = ServiceDebt.objects.select_related("parcela", "persona").all()
    serializer_class = ServiceDebtSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ["parcela__codigo_parcela"]
    filterset_fields = ["parcela", "estado_pago", "tipo_servicio"]
    ordering_fields = ["created_at", "saldo_total"]
    required_roles_per_action = {
        "list": UserRole.CONSULTA,
        "retrieve": UserRole.CONSULTA,
        "create": UserRole.OPERADOR,
        "update": UserRole.OPERADOR,
        "partial_update": UserRole.OPERADOR,
        "destroy": UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {"*": BLOCKED_ACTOR_TYPES}


class PaymentAgreementViewSet(CachedModelViewSet):
    queryset = PaymentAgreement.objects.select_related("parcela").all()
    serializer_class = PaymentAgreementSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ["parcela__codigo_parcela", "empresa", "tipo", "detalle"]
    filterset_fields = ["parcela", "estado_pago"]
    ordering_fields = ["created_at", "fecha_vencimiento", "saldo_monto"]
    required_roles_per_action = {
        "list": UserRole.CONSULTA,
        "retrieve": UserRole.CONSULTA,
        "create": UserRole.OPERADOR,
        "update": UserRole.OPERADOR,
        "partial_update": UserRole.OPERADOR,
        "destroy": UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {"*": BLOCKED_ACTOR_TYPES}


class UnpaidFineViewSet(CachedModelViewSet):
    queryset = UnpaidFine.objects.select_related("parcela").all()
    serializer_class = UnpaidFineSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ["parcela__codigo_parcela", "empresa", "tipo", "detalle"]
    filterset_fields = ["parcela", "estado_pago"]
    ordering_fields = ["created_at", "fecha_vencimiento", "saldo_monto"]
    required_roles_per_action = {
        "list": UserRole.CONSULTA,
        "retrieve": UserRole.CONSULTA,
        "create": UserRole.OPERADOR,
        "update": UserRole.OPERADOR,
        "partial_update": UserRole.OPERADOR,
        "destroy": UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {"*": BLOCKED_ACTOR_TYPES}


class FinancialMovementViewSet(CachedModelViewSet):
    queryset = FinancialMovement.objects.select_related("parcela", "persona").all()
    serializer_class = FinancialMovementSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ["parcela__codigo_parcela", "persona__nombre_completo", "reference", "description", "source_label"]
    filterset_fields = ["parcela", "movement_type", "category", "is_confirmed", "payment_method"]
    ordering_fields = ["occurred_at", "created_at", "amount"]
    required_roles_per_action = {
        "list": UserRole.CONSULTA,
        "retrieve": UserRole.CONSULTA,
        "create": UserRole.OPERADOR,
        "update": UserRole.OPERADOR,
        "partial_update": UserRole.OPERADOR,
        "destroy": UserRole.ADMINISTRADOR,
    }
    disallowed_actor_types_per_action = {"*": BLOCKED_ACTOR_TYPES}
