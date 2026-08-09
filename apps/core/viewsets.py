import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework import viewsets
from rest_framework.response import Response

from apps.core.cache_utils import bump_api_cache_epoch, get_api_cache_epoch


class CachedReadMixin:
    cache_list_timeout = None
    cache_retrieve_timeout = None
    cache_max_payload_bytes = None
    cacheable_actions = {'list', 'retrieve'}

    def get_cache_timeout(self, action: str) -> int:
        if action == 'list':
            timeout = self.cache_list_timeout
            if timeout is None:
                timeout = getattr(settings, 'API_LIST_CACHE_SECONDS', 0)
            return int(timeout or 0)
        if action == 'retrieve':
            timeout = self.cache_retrieve_timeout
            if timeout is None:
                timeout = getattr(settings, 'API_DETAIL_CACHE_SECONDS', 0)
            return int(timeout or 0)
        return 0

    def get_cache_namespace(self) -> str:
        queryset = getattr(self, 'queryset', None)
        model = getattr(queryset, 'model', None)
        if model is None:
            try:
                model = self.get_queryset().model
            except Exception:
                model = None
        if model is not None:
            return model._meta.label_lower
        return self.__class__.__name__

    def get_response_cache_key(self, request, action: str) -> str:
        user = getattr(request, 'user', None)
        user_scope = ':'.join(
            [
                str(getattr(user, 'id', 'anon') or 'anon'),
                str(getattr(user, 'role', '') or ''),
                str(getattr(user, 'actor_type', '') or ''),
            ]
        )
        raw_key = '|'.join(
            [
                self.get_cache_namespace(),
                action,
                str(get_api_cache_epoch()),
                user_scope,
                request.get_full_path(),
            ]
        )
        digest = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()
        return f'api:response:{digest}'

    def should_use_response_cache(self, request, action: str) -> bool:
        if action not in self.cacheable_actions:
            return False
        if request.method != 'GET':
            return False
        if request.query_params.get('_fresh') in {'1', 'true', 'yes'}:
            return False
        if 'no-cache' in request.headers.get('Cache-Control', '').lower():
            return False
        return self.get_cache_timeout(action) > 0

    def should_store_response_cache(self, response) -> bool:
        if response.status_code != 200:
            return False
        if response.streaming:
            return False
        max_bytes = self.cache_max_payload_bytes
        if max_bytes is None:
            max_bytes = getattr(settings, 'API_CACHE_MAX_PAYLOAD_BYTES', 0)
        if not max_bytes:
            return True
        try:
            payload = json.dumps(response.data, cls=DjangoJSONEncoder, ensure_ascii=False)
        except (TypeError, ValueError):
            return False
        return len(payload.encode('utf-8')) <= int(max_bytes)

    def cached_response(self, request, action: str, response_factory, *args, **kwargs):
        if not self.should_use_response_cache(request, action):
            return response_factory(request, *args, **kwargs)

        cache_key = self.get_response_cache_key(request, action)
        cached_payload = cache.get(cache_key)
        if cached_payload is not None:
            response = Response(cached_payload)
            response['X-Foresta-Cache'] = 'HIT'
            return response

        response = response_factory(request, *args, **kwargs)
        if self.should_store_response_cache(response):
            cache.set(cache_key, response.data, timeout=self.get_cache_timeout(action))
            response['X-Foresta-Cache'] = 'MISS'
        return response

    def list(self, request, *args, **kwargs):
        return self.cached_response(request, 'list', super().list, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return self.cached_response(request, 'retrieve', super().retrieve, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and response.status_code < 400:
            bump_api_cache_epoch()
        return response


class CachedModelViewSet(CachedReadMixin, viewsets.ModelViewSet):
    pass


class CachedReadOnlyModelViewSet(CachedReadMixin, viewsets.ReadOnlyModelViewSet):
    pass
