from django.conf import settings
from django.core.cache import cache
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserRole
from apps.api.services.dashboard_analytics import DashboardAnalyticsService
from apps.core.cache_utils import request_cache_key
from apps.core.permissions import has_role_at_least


class DashboardSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not has_role_at_least(request.user, UserRole.CONSULTA):
            return Response({'detail': 'No autorizado'}, status=403)

        cache_timeout = settings.DASHBOARD_CACHE_SECONDS
        cache_key = request_cache_key('dashboard:summary', request)
        if cache_timeout:
            cached_payload = cache.get(cache_key)
            if cached_payload is not None:
                return Response(cached_payload)

        service = DashboardAnalyticsService.from_request(request)
        payload = service.build()
        if cache_timeout:
            cache.set(cache_key, payload, timeout=cache_timeout)
        return Response(payload)
