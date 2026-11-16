"""Bakong KHQR for the checkout total. Payment is never polled; the shopper may ask once per click (services/payment_check.py)."""
import base64
import io
import time
from decimal import ROUND_HALF_UP, Decimal

from flask import current_app


class KHQRConfigError(RuntimeError):
    pass


# Dynamic codes stay valid for the same window the checkout session reuses them.
_QR_LIFETIME_MS = 12 * 60 * 60 * 1000


def _merchant():
    cfg = current_app.config
    account = cfg.get("BAKONG_ACCOUNT_ID", "").strip()
    name = (cfg.get("MERCHANT_NAME") or cfg.get("SHOP_NAME", "")).strip()
    city = cfg.get("MERCHANT_CITY", "").strip()
    if not account or not name or not city:
        raise KHQRConfigError(
            "KHQR is not configured. Set BAKONG_ACCOUNT_ID, MERCHANT_NAME and MERCHANT_CITY."
        )
    if "@" not in account:
        raise KHQRConfigError("BAKONG_ACCOUNT_ID must look like name@bank.")
    return account, name[:25], city[:15]


def _tlv(tag, value):
    value = str(value)
    return f"{tag}{len(value):02d}{value}"


def _crc16(data):
    """CRC-16/CCITT-FALSE over the payload plus the CRC tag, as the Bakong SDK does."""
    crc = 0xFFFF
    for byte in (data + "6304").encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def build_payload(total, reference):
    """Return the EMV KHQR string for a USD amount.

    The string follows the NBC KHQR SDK: USD amounts keep two decimal places,
    and tag 62 subfields are in ascending tag order (bill, store, terminal).
    A bank app rejects the other shape as a transaction it cannot find.
    """
    account, name, city = _merchant()
    amount = Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise KHQRConfigError("The cart total must be above zero to create a KHQR code.")
    bill = str(reference).strip()[:25]
    if not bill:
        raise KHQRConfigError("A payment reference is required to create a KHQR code.")
    created = int(time.time() * 1000)
    expires = created + _QR_LIFETIME_MS
    store = current_app.config["SHOP_NAME"].strip()[:25]
    fields = [
        _tlv("00", "01"),
        _tlv("01", "12"),
        _tlv("29", _tlv("00", account)),
        _tlv("52", "5999"),
        _tlv("53", "840"),
        _tlv("54", f"{amount:.2f}"),
        _tlv("58", "KH"),
        _tlv("59", name),
        _tlv("60", city),
        _tlv("62", _tlv("01", bill) + _tlv("03", store) + _tlv("07", "Web")),
        _tlv("99", _tlv("00", created) + _tlv("01", expires)),
    ]
    body = "".join(fields)
    return body + _tlv("63", _crc16(body))


def payload_md5(payload):
    """The hash Bakong indexes the transaction by."""
    from bakong_khqr import KHQR

    return KHQR().generate_md5(payload)


def render_png(payload):
    """A plain QR of the exact payload. The styled card resamples the modules and covers the center, so bank apps decode a different string."""
    import qrcode
    import qrcode.constants
    from qrcode.image.pil import PilImage

    code = qrcode.QRCode(
        border=4,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    code.add_data(payload)
    code.make(fit=True)
    image = code.make_image(image_factory=PilImage, fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def data_uri(payload):
    return "data:image/png;base64," + base64.b64encode(render_png(payload)).decode("ascii")
