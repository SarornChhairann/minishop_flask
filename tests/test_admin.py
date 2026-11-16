import io
from decimal import Decimal

from app.extensions import db
from app.models import Product


def login(client, password="secret"):
    return client.post("/admin/login", data={"username": "admin", "password": password})


def test_admin_requires_login(client):
    resp = client.get("/admin/products")
    assert resp.status_code == 302 and "/admin/login" in resp.headers["Location"]


def test_wrong_password_is_rejected(client):
    login(client, "nope")
    assert client.get("/admin/products").status_code == 302


def test_create_edit_delete_product(client, png_bytes):
    login(client)
    resp = client.post("/admin/products/new", data={
        "name": "Stone Vase", "description": "Grey soapstone.", "price": "46.00",
        "stock": "9", "status": "active", "image": (io.BytesIO(png_bytes()), "vase.png"),
    }, content_type="multipart/form-data")
    assert resp.status_code == 302
    product = db.session.execute(db.select(Product)).scalar_one()
    assert product.image_original_url.startswith("/static/uploads/original/")
    assert product.image_thumb_url.startswith("/static/uploads/thumb/")
    assert product.price == Decimal("46.00")

    resp = client.post(f"/admin/products/{product.id}/edit", data={
        "name": "Stone Vase", "description": "Grey soapstone.", "price": "50.00",
        "stock": "4", "status": "inactive",
    }, content_type="multipart/form-data")
    assert resp.status_code == 302
    db.session.expire_all()
    product = db.session.get(Product, product.id)
    assert (product.price, product.stock, product.status) == (Decimal("50.00"), 4, "inactive")
    assert product.image_thumb_url  # kept when no new file was sent

    assert client.post(f"/admin/products/{product.id}/delete").status_code == 302
    assert db.session.execute(db.select(Product)).first() is None


def test_non_image_upload_is_rejected(client):
    login(client)
    resp = client.post("/admin/products/new", data={
        "name": "Fake", "description": "x", "price": "1.00", "stock": "1", "status": "active",
        "image": (io.BytesIO(b"not an image"), "fake.png"),
    }, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert db.session.execute(db.select(Product)).first() is None


def test_orders_pages_render(client, make_product):
    login(client)
    assert client.get("/admin/orders").status_code == 200
    assert client.get("/admin/orders/999").status_code == 404
