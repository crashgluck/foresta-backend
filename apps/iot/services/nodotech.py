import json
import logging
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class NodotechClientError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        details: Any = None,
        upstream: bool = True,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details
        self.upstream = upstream


class NodotechConfigurationError(NodotechClientError):
    def __init__(self, message: str):
        super().__init__(message, status_code=503, upstream=False)


@dataclass(frozen=True)
class NodotechAuthTokens:
    access: str
    refresh: str = ''


class NodotechClient:
    access_cache_key = 'nodotech:access_token'
    refresh_cache_key = 'nodotech:refresh_token'

    def __init__(
        self,
        *,
        base_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
        timeout: int | float | None = None,
    ):
        self.base_url = (base_url or settings.NODOTECH_API_BASE_URL).rstrip('/')
        self.email = email if email is not None else settings.NODOTECH_EMAIL
        self.password = password if password is not None else settings.NODOTECH_PASSWORD
        self.timeout = timeout if timeout is not None else settings.NODOTECH_REQUEST_TIMEOUT

    def list_components(self):
        return self._authenticated_request('GET', '/iot/components/')

    def set_relay(self, component_id: int, desired_state: str):
        return self._send_component_command(
            component_id,
            {
                'command': 'SET_RELAY',
                'desired_state': desired_state,
            },
        )

    def pulse_relay(self, component_id: int, pulse_ms: int = 700):
        return self._send_component_command(
            component_id,
            {
                'command': 'PULSE_RELAY',
                'pulse_ms': pulse_ms,
            },
        )

    def command_component(self, component_id: int, payload: dict[str, Any]):
        return self._send_component_command(component_id, payload)

    def _send_component_command(self, component_id: int, payload: dict[str, Any]):
        return self._authenticated_request(
            'POST',
            f'/iot/components/{component_id}/commands/',
            payload,
        )

    def _authenticated_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ):
        token = self._get_access_token()
        try:
            return self._request(method, path, payload, access_token=token)
        except NodotechClientError as exc:
            if exc.status_code != 401:
                raise

        cache.delete_many([self.access_cache_key, self.refresh_cache_key])
        token = self._login().access
        return self._request(method, path, payload, access_token=token)

    def _get_access_token(self) -> str:
        token = cache.get(self.access_cache_key)
        if token:
            return token

        refresh = cache.get(self.refresh_cache_key)
        if refresh:
            try:
                return self._refresh_access_token(refresh).access
            except NodotechClientError:
                logger.info('No se pudo refrescar token Nodotech; se intentara login.')

        return self._login().access

    def _login(self) -> NodotechAuthTokens:
        if not self.email or not self.password:
            raise NodotechConfigurationError(
                'NODOTECH_EMAIL y NODOTECH_PASSWORD deben estar configurados.'
            )

        data = self._request(
            'POST',
            '/auth/login/',
            {
                'email': self.email,
                'password': self.password,
            },
            authenticated=False,
        )
        return self._cache_tokens(data)

    def _refresh_access_token(self, refresh_token: str) -> NodotechAuthTokens:
        data = self._request(
            'POST',
            '/auth/refresh/',
            {'refresh': refresh_token},
            authenticated=False,
        )
        if 'refresh' not in data:
            data['refresh'] = refresh_token
        return self._cache_tokens(data)

    def _cache_tokens(self, data: dict[str, Any]) -> NodotechAuthTokens:
        access = data.get('access') or ''
        refresh = data.get('refresh') or ''
        if not access:
            raise NodotechClientError(
                'Nodotech no retorno access token.',
                status_code=502,
                details={'code': 'missing_access_token'},
            )

        cache.set(
            self.access_cache_key,
            access,
            timeout=settings.NODOTECH_ACCESS_TOKEN_CACHE_SECONDS,
        )
        if refresh:
            cache.set(
                self.refresh_cache_key,
                refresh,
                timeout=settings.NODOTECH_REFRESH_TOKEN_CACHE_SECONDS,
            )
        return NodotechAuthTokens(access=access, refresh=refresh)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        access_token: str = '',
        authenticated: bool = True,
    ):
        if not self.base_url:
            raise NodotechConfigurationError('NODOTECH_API_BASE_URL debe estar configurado.')

        url = f'{self.base_url}/{path.lstrip("/")}'
        body = None
        headers = {
            'Accept': 'application/json',
        }
        if payload is not None:
            body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        if authenticated and access_token:
            headers['Authorization'] = f'Bearer {access_token}'

        request = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return self._parse_response(response.read(), response.status)
        except urllib.error.HTTPError as exc:
            details = self._parse_error_body(exc)
            message = self._extract_error_message(details) or f'Nodotech respondio HTTP {exc.code}.'
            raise NodotechClientError(
                message,
                status_code=exc.code,
                details=details,
            ) from exc
        except urllib.error.URLError as exc:
            raise NodotechClientError(
                f'No se pudo conectar con Nodotech: {exc.reason}',
                status_code=502,
                details={'reason': str(exc.reason)},
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise NodotechClientError(
                'Timeout conectando con Nodotech.',
                status_code=504,
                details={'reason': 'timeout'},
            ) from exc

    def _parse_response(self, raw_body: bytes, status_code: int):
        text = raw_body.decode('utf-8') if raw_body else ''
        if not text.strip():
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise NodotechClientError(
                'Nodotech respondio JSON invalido.',
                status_code=502,
                details={'status_code': status_code},
            ) from exc

    def _parse_error_body(self, exc: urllib.error.HTTPError):
        raw_body = exc.read()
        if not raw_body:
            return {}
        try:
            return json.loads(raw_body.decode('utf-8'))
        except json.JSONDecodeError:
            return {'raw': raw_body.decode('utf-8', errors='replace')}

    def _extract_error_message(self, details):
        if isinstance(details, dict):
            return details.get('message') or details.get('detail') or details.get('error')
        return None
