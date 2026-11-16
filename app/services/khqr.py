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


def _asset(name):
    from importlib import resources

    return resources.files("bakong_khqr.sdk.assets").joinpath(name).read_bytes()


def _usd_amount(raw):
    """KHQR cards print USD as 1.234,56."""
    whole, cents = f"{float(raw):.2f}".split(".")
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    return ".".join(reversed(groups)) + "," + cents


def render_png(payload):
    """The Bakong KHQR card: red header, name, amount, then the code.

    The QR is scaled by whole pixels. The package resamples it and smears the
    modules, so a bank camera reads a different string.
    """
    import qrcode
    import qrcode.constants
    from PIL import Image, ImageDraw, ImageFont
    from qrcode.image.pil import PilImage

    from bakong_khqr.sdk.emv_parser import EMVParser

    scale = 2
    width, height = 300 * scale, 450 * scale
    header = 60 * scale
    parsed = EMVParser(payload)
    merchant = parsed.get("59") or "Unknown"
    amount = float(parsed.get("54") or "0")
    currency = "USD" if (parsed.get("53") or "840") == "840" else "KHR"

    code = qrcode.QRCode(border=4, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_H)
    code.add_data(payload)
    code.make(fit=True)
    qr_img = code.make_image(image_factory=PilImage, fill_color="black", back_color="white")
    qr_img = qr_img.convert("RGB")
    factor = max(1, (280 * scale) // qr_img.size[0])
    qr_side = qr_img.size[0] * factor
    qr_img = qr_img.resize((qr_side, qr_side), Image.Resampling.NEAREST)

    regular = ImageFont.truetype(io.BytesIO(_asset("regular.ttf")), 18 * scale)
    bold = ImageFont.truetype(io.BytesIO(_asset("bold.ttf")), 22 * scale)
    card = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(card)
    draw.rectangle([(0, 0), (width, header)], fill=(204, 0, 0))

    logo = Image.open(io.BytesIO(_asset("logo.png"))).convert("RGBA")
    logo.thumbnail((90 * scale, 21 * scale), Image.Resampling.LANCZOS)
    card.paste(logo, ((width - logo.size[0]) // 2, (header - logo.size[1]) // 2), logo)

    draw.text((32 * scale, 80 * scale), merchant, fill="black", font=regular)
    amount_text = _usd_amount(amount) if currency == "USD" else f"{amount:,.0f}"
    draw.text((30 * scale, 110 * scale), amount_text, fill="black", font=bold)
    if amount > 0:
        amount_width = draw.textbbox((0, 0), amount_text, font=bold)[2]
        draw.text((30 * scale + amount_width + 5 * scale, 118 * scale), currency, fill="black", font=regular)

    dash_y = 150 * scale
    x = 0
    while x < width:
        draw.line([(x, dash_y), (min(x + 2 * scale, width), dash_y)], fill=(160, 160, 160), width=scale)
        x += 6 * scale

    qr_x = (width - qr_side) // 2
    qr_y = 160 * scale + max(0, (280 * scale - qr_side) // 2)
    card.paste(qr_img, (qr_x, qr_y))

    icon_name = "USD.png" if currency == "USD" and amount > 0 else "KHR.png" if amount > 0 else "khqr.png"
    icon_side = 40 * scale
    icon = Image.open(io.BytesIO(_asset(icon_name))).convert("RGBA")
    icon.thumbnail((icon_side, icon_side), Image.Resampling.LANCZOS)
    pad = Image.new("RGB", icon.size, "white")
    pad.paste(icon, (0, 0), icon)
    card.paste(pad, (qr_x + (qr_side - pad.size[0]) // 2, qr_y + (qr_side - pad.size[1]) // 2))

    fold = 90 * scale
    draw.polygon([(width - fold, 0), (width, 0), (width, fold)], fill=(204, 0, 0))

    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, width, height], radius=15 * scale, fill=255)
    framed = Image.new("RGBA", (width, height))
    framed.paste(card, (0, 0), mask)
    buffer = io.BytesIO()
    framed.save(buffer, format="PNG")
    return buffer.getvalue()


def data_uri(payload):
    return "data:image/png;base64," + base64.b64encode(render_png(payload)).decode("ascii")
