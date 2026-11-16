"""Bakong KHQR for the checkout total. Payment is never polled; the shopper may ask once per click (services/payment_check.py)."""
import base64
from decimal import ROUND_HALF_UP, Decimal

from flask import current_app


class KHQRConfigError(RuntimeError):
    pass


def _merchant():
    cfg = current_app.config
    account = cfg.get("BAKONG_ACCOUNT_ID", "").strip()
    name = (cfg.get("MERCHANT_NAME") or cfg.get("SHOP_NAME", "")).strip()
    city = cfg.get("MERCHANT_CITY", "").strip()
    if not account or not name or not city:
        raise KHQRConfigError(
            "KHQR is not configured. Set BAKONG_ACCOUNT_ID, MERCHANT_NAME and MERCHANT_CITY."
        )
    return account, name[:25], city[:15]


def build_payload(total, reference):
    """Return the EMV KHQR string for a USD amount."""
    from bakong_khqr import KHQR

    account, name, city = _merchant()
    amount = Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise KHQRConfigError("The cart total must be above zero to create a KHQR code.")
    payload = KHQR().create_qr(
        amount=float(amount),
        account_id=account,
        merchant_name=name,
        merchant_city=city,
        currency="USD",
        store_label=current_app.config["SHOP_NAME"][:25],
        bill_number=str(reference)[:25],
        terminal_label="Web",
    )
    return str(payload)


def payload_md5(payload):
    """The hash Bakong indexes the transaction by."""
    from bakong_khqr import KHQR

    return KHQR().generate_md5(payload)


def render_png(payload):
    from bakong_khqr import KHQR

    return KHQR().qr_image(payload, format="bytes")


def data_uri(payload):
    return "data:image/png;base64," + base64.b64encode(render_png(payload)).decode("ascii")
