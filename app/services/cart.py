"""Guest cart kept in the signed Flask session.

The session holds only {"<product_id>": quantity}. Names, prices, stock and
status are always read from the database, so an admin edit is never stale here.
"""
from dataclasses import dataclass
from decimal import Decimal

from flask import session

from ..extensions import db
from ..models import Product

SESSION_KEY = "cart"
MAX_QUANTITY = 99


@dataclass
class CartLine:
    product: Product
    quantity: int

    @property
    def subtotal(self):
        return self.product.price * self.quantity

    @property
    def exceeds_stock(self):
        return self.quantity > self.product.stock


def _raw():
    raw = session.get(SESSION_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def _save(cart):
    session[SESSION_KEY] = cart
    session.modified = True


def quantities():
    """Return {product_id: quantity} with ids as ints."""
    result = {}
    for key, qty in _raw().items():
        try:
            pid, qty = int(key), int(qty)
        except (TypeError, ValueError):
            continue
        if qty > 0:
            result[pid] = qty
    return result


def add(product_id, quantity):
    cart = _raw()
    key = str(product_id)
    cart[key] = min(int(cart.get(key, 0)) + quantity, MAX_QUANTITY)
    _save(cart)
    return cart[key]


def set_quantity(product_id, quantity):
    cart = _raw()
    key = str(product_id)
    if quantity <= 0:
        cart.pop(key, None)
    else:
        cart[key] = min(quantity, MAX_QUANTITY)
    _save(cart)


def remove(product_id):
    set_quantity(product_id, 0)


def clear():
    session.pop(SESSION_KEY, None)


def count():
    return sum(quantities().values())


def lines():
    """Cart lines for active products that still exist, plus the total from database prices."""
    qty_by_id = quantities()
    if not qty_by_id:
        return [], Decimal("0.00")
    products = db.session.execute(
        db.select(Product).where(Product.id.in_(qty_by_id), Product.status == "active")
    ).scalars()
    by_id = {p.id: p for p in products}
    result = [CartLine(by_id[pid], qty) for pid, qty in qty_by_id.items() if pid in by_id]
    total = sum((line.subtotal for line in result), Decimal("0.00"))
    return result, total
