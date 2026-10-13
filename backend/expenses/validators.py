"""FR-15 / NFR-5: expense receipt checks. Images are checked with Pillow
(the product image validator); PDFs by their file signature. The client's
filename and content type are ignored."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from catalog.validators import validate_product_image

PDF_SIGNATURE = b"%PDF-"
# Phone cameras take photos around 4000–8000 px wide.
MAX_DIMENSION = 10000


def validate_receipt(upload):
    """Return the extension to store the file under, or raise ValidationError."""
    max_bytes = settings.EXPENSE_RECEIPT_MAX_BYTES
    if upload.size > max_bytes:
        raise ValidationError(
            _("The file is too large. The limit is %(mb)s MB.") % {"mb": max_bytes // (1024 * 1024)}
        )

    upload.seek(0)
    head = upload.read(len(PDF_SIGNATURE))
    upload.seek(0)
    if head == PDF_SIGNATURE:
        return "pdf"
    try:
        return validate_product_image(upload, max_bytes=max_bytes, max_dimension=MAX_DIMENSION)
    except ValidationError:
        raise ValidationError(_("Use a photo (JPEG, PNG or WebP) or a PDF of the receipt."))
