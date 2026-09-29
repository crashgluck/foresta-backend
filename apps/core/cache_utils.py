import hashlib

from django.core.cache import cache
from rest_framework.response import Response

API_CACHE_EPOCH_KEY = 'api:response-cache:epoch'


def request_cache_key(prefix: str, request, *, vary_by_user: bool = False, include_api_epoch: bool = True) -> str:
    query_string = request.META.get('QUERY_STRING', '')
    digest = hashlib.sha256(query_string.encode('utf-8')).hexdigest()[:20]
    epoch = f':v{get_api_cache_epoch()}' if include_api_epoch else ''
    if vary_by_user:
        user_id = getattr(getattr(request, 'user', None), 'id', 'anon') or 'anon'
        return f'{prefix}{epoch}:user:{user_id}:{digest}'
    return f'{prefix}{epoch}:{digest}'


def get_api_cache_epoch() -> int:
    epoch = cache.get(API_CACHE_EPOCH_KEY)
    if epoch is None:
        cache.add(API_CACHE_EPOCH_KEY, 1, timeout=None)
        epoch = cache.get(API_CACHE_EPOCH_KEY, 1)
    return int(epoch or 1)


def bump_api_cache_epoch() -> int:
    cache.add(API_CACHE_EPOCH_KEY, 1, timeout=None)
    try:
        return int(cache.incr(API_CACHE_EPOCH_KEY))
    except ValueError:
        cache.set(API_CACHE_EPOCH_KEY, 2, timeout=None)
        return 2


def cached_api_response(prefix: str, request, timeout: int, payload_factory, *, vary_by_user: bool = False) -> Response:
    timeout = int(timeout or 0)
    if (
        request.method != 'GET'
        or timeout <= 0
        or request.query_params.get('_fresh') in {'1', 'true', 'yes'}
        or 'no-cache' in request.headers.get('Cache-Control', '').lower()
    ):
        return Response(payload_factory())

    cache_key = request_cache_key(prefix, request, vary_by_user=vary_by_user)
    cached_payload = cache.get(cache_key)
    if cached_payload is not None:
        response = Response(cached_payload)
        response['X-Foresta-Cache'] = 'HIT'
        return response

    payload = payload_factory()
    cache.set(cache_key, payload, timeout=timeout)
    response = Response(payload)
    response['X-Foresta-Cache'] = 'MISS'
    return response

