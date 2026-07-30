from django.conf import settings
from django.http import Http404
from django.views.static import serve


def serve_media_file(request, path):
    if not getattr(settings, 'SERVE_MEDIA_FILES', settings.DEBUG):
        raise Http404
    return serve(request, path, document_root=settings.MEDIA_ROOT)
