from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from django.core.files.base import ContentFile
from rest_framework import serializers


MAX_IMAGE_EDGE = 1600
WEBP_QUALITY = 76
JPEG_QUALITY = 82


@dataclass(frozen=True)
class ProcessedGeoImage:
    content: ContentFile
    filename: str
    content_type: str
    size: int
    width: int
    height: int
    original_name: str


def process_geo_asset_photo(uploaded_file) -> ProcessedGeoImage:
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:
        raise serializers.ValidationError('Pillow no esta instalado; no se pudo procesar la imagen.') from exc

    original_name = Path(getattr(uploaded_file, 'name', '') or 'foto').name
    try:
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError) as exc:
        raise serializers.ValidationError('La foto no pudo leerse. Sube una imagen tomada desde el telefono o un JPG/PNG valido.') from exc

    if image.mode not in {'RGB', 'RGBA'}:
        image = image.convert('RGB')

    image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)

    output = BytesIO()
    extension = 'webp'
    content_type = 'image/webp'
    save_kwargs = {'format': 'WEBP', 'quality': WEBP_QUALITY, 'method': 6}
    try:
        image.save(output, **save_kwargs)
    except OSError:
        extension = 'jpg'
        content_type = 'image/jpeg'
        if image.mode != 'RGB':
            image = image.convert('RGB')
        image.save(output, format='JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True)

    payload = output.getvalue()
    return ProcessedGeoImage(
        content=ContentFile(payload),
        filename=f'{uuid4().hex}.{extension}',
        content_type=content_type,
        size=len(payload),
        width=image.width,
        height=image.height,
        original_name=original_name,
    )
