from decimal import Decimal

from app.extensions import db
from app.models import Order, Product
from tests.conftest import GUEST, add_to_cart


def test_checkout_creates_order_and_decrements_stock(client, make_product):
    a = make_product(name="Bowl", price="28.00", stock=5)
    b = make_product(name="Hook", price="14.00", stock=3)
    add_to_cart(client, a.id, 2)
    add_to_cart(client, b.id, 1)

    resp = client.post("/checkout", data=GUEST)
    assert resp.status_code == 302
    order = db.session.execute(db.select(Order)).scalar_one()
    assert resp.headers["Location"].endswith(f"/order/{order.id}")
    assert order.total == Decimal("70.00")
    assert order.customer_name == "Sok Dara"
    assert {(i.product_name, i.quantity, i.unit_price, i.subtotal) for i in order.items} == {
        ("Bowl", 2, Decimal("28.00"), Decimal("56.00")),
        ("Hook", 1, Decimal("14.00"), Decimal("14.00")),
    }
    db.session.expire_all()
    assert db.session.get(Product, a.id).stock == 3
    assert db.session.get(Product, b.id).stock == 2

    page = client.get(f"/order/{order.id}").get_data(as_text=True)
    assert f"#{order.id}" in page and "$70.00" in page
    with client.session_transaction() as sess:
        assert not sess.get("cart")


def test_checkout_refuses_oversell(client, make_product):
    product = make_product(stock=3)
    add_to_cart(client, product.id, 3)
    product.stock = 1  # someone else bought two meanwhile
    db.session.commit()

    resp = client.post("/checkout", data=GUEST)
    assert resp.status_code == 200
    assert db.session.execute(db.select(Order)).first() is None
    db.session.expire_all()
    assert db.session.get(Product, product.id).stock == 1


def test_invalid_form_leaves_stock(client, make_product):
    product = make_product(stock=4)
    add_to_cart(client, product.id, 2)
    resp = client.post("/checkout", data={**GUEST, "email": "not-an-email"})
    assert resp.status_code == 200
    assert db.session.execute(db.select(Order)).first() is None
    db.session.expire_all()
    assert db.session.get(Product, product.id).stock == 4


def test_order_page_is_private_to_the_buyer(app, client, make_product):
    product = make_product(stock=2)
    add_to_cart(client, product.id, 1)
    client.post("/checkout", data=GUEST)
    order = db.session.execute(db.select(Order)).scalar_one()
    assert app.test_client().get(f"/order/{order.id}").status_code == 404


def test_empty_cart_redirects(client):
    assert client.get("/checkout").status_code == 302
