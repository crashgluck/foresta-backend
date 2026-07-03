from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.thread_local import set_current_user


SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_auth = JWTAuthentication()

    def __call__(self, request):
        resolved_user = getattr(request, 'user', None)

        if not getattr(resolved_user, 'is_authenticated', False) and self._should_authenticate_early(request):
            try:
                header = self.jwt_auth.get_header(request)
                if header:
                    raw_token = self.jwt_auth.get_raw_token(header)
                    if raw_token:
                        validated_token = self.jwt_auth.get_validated_token(raw_token)
                        resolved_user = self.jwt_auth.get_user(validated_token)
            except Exception:
                resolved_user = getattr(request, 'user', None)

        request.audit_user = resolved_user
        set_current_user(resolved_user)
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)

    def _should_authenticate_early(self, request) -> bool:
        if request.method.upper() not in SAFE_METHODS:
            return True
        if settings.CURRENT_USER_AUTHENTICATE_SAFE_METHODS:
            return True
        return settings.AUDIT_TRAIL_ENABLED and settings.AUDIT_LOG_READS
