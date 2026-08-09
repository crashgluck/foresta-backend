import hashlib

from django.core.cache import cache

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

