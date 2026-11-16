import json

import httpx
import pytest
import respx

from app.extensions import db
from app.models import Order
from app.services.khqr import payload_md5
from tests.conftest import GUEST, add_to_cart

PROXY = "https://proxy.test"


@pytest.fixture
def merchant(app):
    app.config.update(BAKONG_ACCOUNT_ID="shop@aclb", MERCHANT_NAME="Test Shop", MERCHANT_CITY="Phnom Penh")


@pytest.fixture
def proxy(app, merchant):
    app.config.update(BAKONG_PROXY_URL=PROXY, BAKONG_PROXY_SECRET="s3cret")
    with respx.mock(base_url=PROXY) as mock:
        yield mock


def _issued_payload(client):
    with client.session_transaction() as sess:
        return sess["checkout_qr"]["payload"]


def test_check_sends_the_session_md5_once(client, make_product, proxy):
    route = proxy.post("/v1/check").mock(return_value=httpx.Response(
        200, json={"status": "paid", "message": "Getting transaction successfully."}))
    add_to_cart(client, make_product(price="12.50").id, 2)
    client.get("/checkout")
    payload = _issued_payload(client)

    page = client.post("/checkout/payment-status", data={"md5": "f" * 32}).get_data(as_text=True)

    assert route.call_count == 1
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer s3cret"
    assert json.loads(sent.content) == {"md5": payload_md5(payload)}
    assert "Paid. You can place your order." in page
    assert _issued_payload(client) == payload


def test_unpaid(client, make_product, proxy):
    proxy.post("/v1/check").mock(return_value=httpx.Response(
        200, json={"status": "unpaid", "message": "Transaction could not be found."}))
    add_to_cart(client, make_product().id)
    page = client.post("/checkout/payment-status").get_data(as_text=True)
    assert "Not paid yet" in page


def test_proxy_down_is_reported(client, make_product, proxy):
    proxy.post("/v1/check").mock(side_effect=httpx.ConnectError("refused"))
    add_to_cart(client, make_product().id)
    resp = client.post("/checkout/payment-status")
    assert resp.status_code == 200
    assert "Could not check the payment" in resp.get_data(as_text=True)


def test_unconfigured_proxy_still_shows_qr(client, make_product, merchant):
    add_to_cart(client, make_product().id)
    with respx.mock(assert_all_called=False) as mock:
        page = client.post("/checkout/payment-status").get_data(as_text=True)
    assert not mock.calls
    assert "not configured" in page
    assert "khqr__image" in page


def test_qr_is_stable_and_saved_on_the_order(client, make_product, merchant):
    product = make_product(price="9.00", stock=5)
    add_to_cart(client, product.id)
    client.get("/checkout")
    first = _issued_payload(client)
    client.get("/checkout")
    assert _issued_payload(client) == first

    add_to_cart(client, product.id)  # total changes, so the code must too
    client.get("/checkout")
    second = _issued_payload(client)
    assert second != first

    client.post("/checkout", data=GUEST)
    assert db.session.execute(db.select(Order)).scalar_one().khqr_payload == second


def test_empty_cart_redirects(client):
    assert client.post("/checkout/payment-status").status_code == 302
