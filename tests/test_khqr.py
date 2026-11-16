import pytest

from app.services.khqr import KHQRConfigError, build_payload, render_png


def test_missing_merchant_settings_raise(app):
    with pytest.raises(KHQRConfigError):
        build_payload("10.00", "REF1")


def test_payload_and_png(app):
    app.config.update(BAKONG_ACCOUNT_ID="shop@aclb", MERCHANT_NAME="Test Shop", MERCHANT_CITY="Phnom Penh")
    payload = build_payload("12.50", "REF1")
    assert "shop@aclb" in payload and "12.5" in payload
    assert render_png(payload)[:8] == b"\x89PNG\r\n\x1a\n"
