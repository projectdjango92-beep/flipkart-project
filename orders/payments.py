"""Customer-facing UPI instructions, never payment verification."""
import base64
from io import BytesIO
from urllib.parse import urlencode

import qrcode
from django.conf import settings


def upi_is_configured():
    return bool(settings.BHARAT_MART_UPI_ID and "@" in settings.BHARAT_MART_UPI_ID)


def payment_reference(order):
    return f"BM-{order.pk}"


def upi_intent(order):
    """Build an intent entirely from server-side order values."""
    if not upi_is_configured():
        raise ValueError("Online UPI payments are not configured.")
    return "upi://pay?" + urlencode({
        "pa": settings.BHARAT_MART_UPI_ID,
        "pn": settings.BHARAT_MART_UPI_NAME,
        "tr": payment_reference(order),
        "tn": f"Bharat Mart order {order.pk}",
        "am": f"{order.total_amount:.2f}",
        "cu": "INR",
    })


def upi_qr_code(order):
    """Create a dynamic PNG data URI for this order's UPI intent."""
    image = qrcode.make(upi_intent(order))
    output = BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
