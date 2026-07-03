import json
from typing import Any

from django.conf import settings

from apps.audits.models import AuditAction, AuditEventLog, SessionAction, UserSessionLog

SENSITIVE_KEYS = {'password', 'old_password', 'new_password', 'access', 'refresh', 'token'}


def get_client_ip(request) -> str:
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _trim_string(value: str, max_length: int = 500) -> str:
    if len(value) <= max_length:
        return value
    return f'{value[:max_length]}...'


def sanitize_value(value: Any):
    if isinstance(value, dict):
        return {key: ('***' if key.lower() in SENSITIVE_KEYS else sanitize_value(val)) for key, val in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item) for item in value[:100]]
    if isinstance(value, str):
        return _trim_string(value)
    return value


def parse_request_payload(request):
    if not settings.AUDIT_LOG_PAYLOAD:
        return {}
    if request.method in {'GET', 'HEAD', 'OPTIONS'}:
        return {}

    content_type = (request.content_type or '').lower()
    if 'multipart' in content_type:
        return {'_info': 'multipart payload omitted'}

    body = getattr(request, '_body', None)
    if body is None:
        try:
            body = request.body or b''
        except Exception:
            return {'_info': 'payload unavailable'}
    if not body:
        return {}
    if settings.AUDIT_MAX_PAYLOAD_BYTES <= 0 or len(body) > settings.AUDIT_MAX_PAYLOAD_BYTES:
        return {'_info': 'payload omitted by size'}

    try:
        parsed = json.loads(body.decode('utf-8'))
    except Exception:
        return {'_raw': _trim_string(body.decode('utf-8', errors='ignore'), max_length=500)}
    return sanitize_value(parsed)


def build_response_summary(response):
    if response is None:
        return {}
    status_code = getattr(response, 'status_code', 0) or 0
    data = getattr(response, 'data', None)
    summary = {'status_code': status_code}
    if isinstance(data, dict):
        summary['keys'] = list(data.keys())[:20]
    return summary


def create_session_log(*, request, action: str, success: bool, user=None, auth_identifier: str = '', metadata=None):
    if not settings.SESSION_AUDIT_ENABLED:
        return
    if action == SessionAction.REFRESH and not settings.SESSION_AUDIT_LOG_REFRESH:
        return
    try:
        UserSessionLog.objects.create(
            user=user if getattr(user, 'is_authenticated', False) else None,
            action=action,
            success=success,
            auth_identifier=_trim_string(auth_identifier or '', max_length=255),
            ip_address=get_client_ip(request) or None,
            user_agent=_trim_string(request.META.get('HTTP_USER_AGENT', ''), max_length=1000),
            metadata=sanitize_value(metadata or {}),
        )
    except Exception:
        return


def resolve_audit_action(method: str, object_id: str = '') -> str:
    if method == 'GET':
        return AuditAction.RETRIEVE if object_id else AuditAction.LIST
    if method == 'POST':
        return AuditAction.CREATE
    if method in {'PUT', 'PATCH'}:
        return AuditAction.UPDATE
    if method == 'DELETE':
        return AuditAction.DELETE
    return AuditAction.CUSTOM


def create_audit_event(
    *,
    request,
    response,
    action: str | None = None,
    resource: str = '',
    object_id: str = '',
    message: str = '',
):
    request_user = getattr(request, 'audit_user', None) or getattr(request, 'user', None)
    user = request_user if request_user and request_user.is_authenticated else None
    method = request.method.upper()
    status_code = getattr(response, 'status_code', 0) or 0
    resolved_action = action or resolve_audit_action(method, object_id)

    try:
        AuditEventLog.objects.create(
            user=user,
            user_role=getattr(user, 'role', '') if user else '',
            user_actor_type=getattr(user, 'actor_type', '') if user else '',
            action=resolved_action,
            request_method=method,
            request_path=_trim_string(request.path, max_length=255),
            resource=_trim_string(resource, max_length=120),
            object_id=_trim_string(object_id, max_length=64),
            status_code=status_code,
            is_success=200 <= status_code < 400,
            message=_trim_string(message or f'{method} {request.path}', max_length=255),
            ip_address=get_client_ip(request) or None,
            user_agent=_trim_string(request.META.get('HTTP_USER_AGENT', ''), max_length=1000),
            query_params=sanitize_value(dict(request.GET.items())) if settings.AUDIT_LOG_QUERY_PARAMS else {},
            payload=parse_request_payload(request),
            response_summary=build_response_summary(response),
        )
    except Exception:
        return


def get_session_action_from_path(path: str) -> str | None:
    normalized = (path or '').strip().lower()
    if normalized.endswith('/auth/login/'):
        return SessionAction.LOGIN
    if normalized.endswith('/auth/logout/'):
        return SessionAction.LOGOUT
    if normalized.endswith('/auth/refresh/'):
        return SessionAction.REFRESH
    if normalized.endswith('/auth/change-password/'):
        return SessionAction.PASSWORD_CHANGE
    return None
