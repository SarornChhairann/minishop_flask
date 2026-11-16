from decimal import Decimal

from app.extensions import db
from tests.conftest import add_to_cart


def _cart(client):
    with client.session_transaction() as sess:
        return dict(sess.get("cart", {}))


def test_add_update_remove(client, make_product):
    product = make_product(stock=10)
    add_to_cart(client, product.id, 2)
    add_to_cart(client, product.id, 1)
    assert _cart(client) == {str(product.id): 3}

    client.post("/cart", data={"action": "update", "product_id": product.id, "quantity": 5})
    assert _cart(client) == {str(product.id): 5}

    client.post("/cart", data={"action": "remove", "product_id": product.id})
    assert _cart(client) == {}


def test_add_is_capped_by_stock(client, make_product):
    product = make_product(stock=2)
    add_to_cart(client, product.id, 5)
    assert _cart(client) == {str(product.id): 2}


def test_total_uses_database_price(client, make_product):
    product = make_product(price="10.00", stock=10)
    add_to_cart(client, product.id, 2)
    product.price = Decimal("12.50")
    db.session.commit()
    page = client.get("/cart").get_data(as_text=True)
    assert "$25.00" in page


def test_inactive_product_cannot_be_added(client, make_product):
    product = make_product(status="inactive")
    add_to_cart(client, product.id)
    assert _cart(client) == {}
    assert client.get(f"/product/{product.id}").status_code == 404
