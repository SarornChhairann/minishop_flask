import pytest

from app.services.khqr import KHQRConfigError, build_payload, render_png


def test_missing_merchant_settings_raise(app):
    with pytest.raises(KHQRConfigError):
        build_payload("10.00", "REF1")


def test_payload_and_png(app):
    app.config.update(
        BAKONG_ACCOUNT_ID="shop@aclb", MERCHANT_NAME="Test Shop",
        MERCHANT_CITY="Phnom Penh", SHOP_NAME="Test Shop",
    )
    payload = build_payload("12.50", "REF1")
    assert "shop@aclb" in payload
    assert "540512.50" in payload
    assert payload.index("0104REF1") < payload.index("0309Test Shop") < payload.index("0703Web")
    assert payload[-8:-4] == "6304"
    small = build_payload("0.10", "REF1")
    assert "54040.10" in small
    assert render_png(payload)[:8] == b"\x89PNG\r\n\x1a\n"
