import io
from decimal import Decimal

import pytest
from PIL import Image

from app import create_app
from app.extensions import db
from app.models import Product


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_ENGINE_OPTIONS": {},
        "WTF_CSRF_ENABLED": False,
        "STORAGE_BACKEND": "local",
        "LOCAL_UPLOAD_DIR": str(tmp_path / "uploads"),
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "secret",
        "BAKONG_ACCOUNT_ID": "",
        "MERCHANT_NAME": "",
        "MERCHANT_CITY": "",
        "BAKONG_PROXY_URL": "",
        "BAKONG_PROXY_SECRET": "",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_product(app):
    def _make(name="Test Item", price="10.00", stock=5, status="active"):
        product = Product(name=name, description=f"{name} description", price=Decimal(price),
                          stock=stock, status=status)
        db.session.add(product)
        db.session.commit()
        return product
    return _make


@pytest.fixture
def png_bytes():
    def _png(size=(2400, 1800), mode="RGBA"):
        buf = io.BytesIO()
        Image.new(mode, size, (200, 120, 40, 255) if mode == "RGBA" else (200, 120, 40)).save(buf, "PNG")
        return buf.getvalue()
    return _png


def add_to_cart(client, product_id, quantity=1):
    return client.post("/cart", data={"action": "add", "product_id": product_id, "quantity": quantity})


GUEST = {
    "full_name": "Sok Dara",
    "email": "dara@example.com",
    "phone": "+855 12 345 678",
    "address": "Street 51, Phnom Penh",
}
