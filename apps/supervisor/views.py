import csv
from datetime import datetime

from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.accounts.models import UserRole
from apps.core.parcel_display import primary_owner_prefetch
from apps.core.permissions import RoleBasedActionPermission
from apps.supervisor.models import NotificationFine, Round, Shift
from apps.supervisor.serializers import NotificationFineSerializer, RoundSerializer, ShiftSerializer


class ShiftViewSet(viewsets.ModelViewSet):
    queryset = Shift.objects.select_related('supervisor').all()
    serializer_class = ShiftSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['name', 'supervisor__username', 'supervisor__first_name', 'supervisor__last_name']
    filterset_fields = ['status', 'supervisor', 'start_datetime']
    ordering_fields = ['start_datetime', 'end_datetime', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }


class RoundViewSet(viewsets.ModelViewSet):
    queryset = Round.objects.select_related('shift', 'guard').all()
    serializer_class = RoundSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['notes', 'guard__username', 'shift__name']
    filterset_fields = ['status', 'shift', 'guard', 'started_at']
    ordering_fields = ['started_at', 'ended_at', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }


class NotificationFineViewSet(viewsets.ModelViewSet):
    queryset = NotificationFine.objects.select_related('parcela', 'persona', 'shift').prefetch_related(primary_owner_prefetch())
    serializer_class = NotificationFineSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['title', 'description', 'parcela__codigo_parcela', 'persona__nombre_completo']
    filterset_fields = ['status', 'parcela', 'issued_at', 'due_date']
    ordering_fields = ['issued_at', 'amount', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(issued_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(issued_at__date__lte=date_to)
        return queryset

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="notificaciones_{datetime.now():%Y%m%d_%H%M%S}.csv"'
        writer = csv.writer(response)
        writer.writerow(['id', 'parcela', 'title', 'amount', 'status', 'issued_at', 'due_date', 'paid_at'])
        for item in queryset:
            writer.writerow(
                [
                    item.id,
                    item.parcela.codigo_parcela if item.parcela_id else '',
                    item.title,
                    item.amount,
                    item.status,
                    item.issued_at.isoformat(),
                    item.due_date.isoformat() if item.due_date else '',
                    item.paid_at.isoformat() if item.paid_at else '',
                ]
            )
        return response

