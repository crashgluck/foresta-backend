from datetime import datetime, time, timedelta

from django.db.models import Count
from django.utils import timezone
from rest_framework import decorators, response, viewsets

from apps.accounts.models import UserRole
from apps.audits.models import AuditEventLog, UserSessionLog
from apps.audits.serializers import AuditEventLogSerializer, UserSessionLogSerializer
from apps.core.permissions import RoleBasedActionPermission
from apps.core.viewsets import CachedReadOnlyModelViewSet


class UserSessionLogViewSet(CachedReadOnlyModelViewSet):
    queryset = UserSessionLog.objects.select_related('user').all()
    serializer_class = UserSessionLogSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'auth_identifier', 'ip_address']
    filterset_fields = ['action', 'success', 'user']
    ordering_fields = ['created_at', 'action']

    required_roles_per_action = {
        'list': UserRole.ADMINISTRADOR,
        'retrieve': UserRole.ADMINISTRADOR,
    }


class AuditEventLogViewSet(CachedReadOnlyModelViewSet):
    queryset = AuditEventLog.objects.select_related('user').all()
    serializer_class = AuditEventLogSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = [
        'user__email',
        'user__first_name',
        'user__last_name',
        'request_path',
        'resource',
        'object_id',
        'message',
    ]
    filterset_fields = ['action', 'request_method', 'status_code', 'is_success', 'resource', 'user']
    ordering_fields = ['created_at', 'status_code', 'action']

    required_roles_per_action = {
        'list': UserRole.ADMINISTRADOR,
        'retrieve': UserRole.ADMINISTRADOR,
        'summary': UserRole.ADMINISTRADOR,
    }

    @decorators.action(detail=False, methods=['get'])
    def summary(self, request):
        now = timezone.now()
        today = now.date()
        day_start = timezone.make_aware(datetime.combine(today, time.min), timezone.get_current_timezone())
        seven_days_ago = now - timedelta(days=7)

        base_qs = self.get_queryset()
        last_7_days = base_qs.filter(created_at__gte=seven_days_ago)

        by_action = list(last_7_days.values('action').annotate(total=Count('id')).order_by('-total'))
        by_method = list(last_7_days.values('request_method').annotate(total=Count('id')).order_by('-total'))

        return response.Response(
            {
                'total_events_7d': last_7_days.count(),
                'total_events_today': base_qs.filter(created_at__gte=day_start).count(),
                'failed_events_7d': last_7_days.filter(is_success=False).count(),
                'successful_events_7d': last_7_days.filter(is_success=True).count(),
                'session_logs_7d': UserSessionLog.objects.filter(created_at__gte=seven_days_ago).count(),
                'actions_breakdown_7d': by_action,
                'methods_breakdown_7d': by_method,
            }
        )
