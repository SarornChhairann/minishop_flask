from datetime import datetime, timezone
from decimal import Decimal

from .extensions import db


def _now():
    return datetime.now(timezone.utc)


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    price = db.Column(db.Numeric(10, 2), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(10), nullable=False, default="active")
    image_original_url = db.Column(db.String(500))
    image_thumb_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)

    @property
    def is_active(self):
        return self.status == "active"

    @property
    def in_stock(self):
        return self.stock > 0


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.Text, nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    khqr_payload = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)

    items = db.relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
    )


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    # Nullable so an order keeps its history after the product is deleted.
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"))
    product_name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    order = db.relationship("Order", back_populates="items")
