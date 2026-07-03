import hashlib


def request_cache_key(prefix: str, request, *, vary_by_user: bool = False) -> str:
    query_string = request.META.get('QUERY_STRING', '')
    digest = hashlib.sha256(query_string.encode('utf-8')).hexdigest()[:20]
    if vary_by_user:
        user_id = getattr(getattr(request, 'user', None), 'id', 'anon') or 'anon'
        return f'{prefix}:user:{user_id}:{digest}'
    return f'{prefix}:{digest}'

