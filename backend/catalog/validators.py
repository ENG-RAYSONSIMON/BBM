"""FR-10 / NFR-5: product image checks. The file's real format is read with
Pillow; the client's filename and content type are ignored."""

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

# Pillow format name -> extension used for the stored file.
ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
MAX_DIMENSION = 4000


def validate_product_image(upload):
    """Return the extension to store the file under, or raise ValidationError."""
    max_bytes = settings.PRODUCT_IMAGE_MAX_BYTES
    if upload.size > max_bytes:
        raise ValidationError(f"Image is too large. The limit is {max_bytes // (1024 * 1024)} MB.")

    try:
        upload.seek(0)
        with Image.open(upload) as image:
            image_format = image.format
            width, height = image.size  # read from the header, before decoding
            if image_format not in ALLOWED_FORMATS:
                raise ValidationError("Use a JPEG, PNG or WebP image.")
            if width > MAX_DIMENSION or height > MAX_DIMENSION:
                raise ValidationError(
                    f"Image is too big. Use at most {MAX_DIMENSION}×{MAX_DIMENSION} pixels."
                )
            image.verify()  # detects truncated or corrupt files
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ValidationError("This file isn't a valid image. Use a JPEG, PNG or WebP image.")
    finally:
        upload.seek(0)

    return ALLOWED_FORMATS[image_format]
