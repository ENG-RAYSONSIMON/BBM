"""FR-10 / NFR-5: product image checks. The file's real format is read with
Pillow; the client's filename and content type are ignored."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from PIL import Image, UnidentifiedImageError

# Pillow format name -> extension used for the stored file.
ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
MAX_DIMENSION = 4000


def validate_product_image(upload, max_bytes=None, max_dimension=MAX_DIMENSION):
    """Return the extension to store the file under, or raise ValidationError.
    `max_bytes` defaults to PRODUCT_IMAGE_MAX_BYTES."""
    max_bytes = max_bytes or settings.PRODUCT_IMAGE_MAX_BYTES
    if upload.size > max_bytes:
        raise ValidationError(
            _("Image is too large. The limit is %(mb)s MB.") % {"mb": max_bytes // (1024 * 1024)}
        )

    try:
        upload.seek(0)
        with Image.open(upload) as image:
            image_format = image.format
            width, height = image.size  # read from the header, before decoding
            if image_format not in ALLOWED_FORMATS:
                raise ValidationError(_("Use a JPEG, PNG or WebP image."))
            if width > max_dimension or height > max_dimension:
                raise ValidationError(
                    _("Image is too big. Use at most %(size)s×%(size)s pixels.") % {"size": max_dimension}
                )
            image.verify()  # detects truncated or corrupt files
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ValidationError(_("This file isn't a valid image. Use a JPEG, PNG or WebP image."))
    finally:
        upload.seek(0)

    return ALLOWED_FORMATS[image_format]
