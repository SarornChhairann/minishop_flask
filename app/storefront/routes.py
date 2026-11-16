import secrets
import time
from decimal import Decimal
from urllib.parse import quote

from flask import abort, current_app, flash, redirect, render_template, request, session, url_for

from ..extensions import db
from ..forms import CheckoutForm
from ..models import Order, OrderItem, Product
from ..services import cart
from ..services.khqr import KHQRConfigError, build_payload, data_uri, payload_md5
from ..services.payment_check import check_payment
from . import bp

PLACED_ORDERS_KEY = "placed_orders"
CHECKOUT_QR_KEY = "checkout_qr"
# KHQR codes expire after a day. Issue a fresh one well before that.
CHECKOUT_QR_MAX_AGE = 12 * 60 * 60


@bp.app_context_processor
def inject_shop():
    return {
        "shop_name": current_app.config["SHOP_NAME"],
        "shop_tagline": current_app.config["SHOP_TAGLINE"],
        "cart_count": cart.count(),
    }


def _active_product_or_404(product_id):
    product = db.session.get(Product, product_id)
    if product is None or not product.is_active:
        abort(404)
    return product


def _parse_int(raw, default):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _parse_quantity(raw, default=1):
    return max(0, min(_parse_int(raw, default), cart.MAX_QUANTITY))


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("storefront.cart_view")


@bp.get("/")
def home():
    products = db.session.execute(
        db.select(Product).where(Product.status == "active").order_by(Product.created_at.desc(), Product.id.desc())
    ).scalars().all()
    return render_template("storefront/home.html", products=products)


@bp.get("/product/<int:product_id>")
def product_detail(product_id):
    product = _active_product_or_404(product_id)
    absolute = url_for("storefront.product_detail", product_id=product.id, _external=True)
    share = {
        "facebook": "https://www.facebook.com/sharer/sharer.php?u=" + quote(absolute, safe=""),
        "telegram": "https://t.me/share/url?url=" + quote(absolute, safe="") + "&text=" + quote(product.name, safe=""),
    }
    return render_template("storefront/product.html", product=product, share=share)


@bp.route("/cart", methods=["GET", "POST"])
def cart_view():
    if request.method == "POST":
        action = request.form.get("action")
        product_id = _parse_int(request.form.get("product_id"), 0)
        if action == "add":
            product = db.session.get(Product, product_id)
            quantity = max(1, _parse_quantity(request.form.get("quantity")))
            if product is None or not product.is_active:
                flash("That product is no longer available.", "error")
            elif not product.in_stock:
                flash(f"{product.name} is out of stock.", "error")
            else:
                already = cart.quantities().get(product.id, 0)
                allowed = max(0, product.stock - already)
                if allowed == 0:
                    flash(f"Your cart already holds all {product.stock} of {product.name}.", "error")
                else:
                    cart.add(product.id, min(quantity, allowed))
                    if quantity > allowed:
                        flash(f"Only {allowed} more of {product.name} available; added {allowed}.", "info")
                    else:
                        flash(f"Added {product.name} to your cart.", "success")
            return redirect(_safe_next(request.form.get("next")))
        if action == "update":
            cart.set_quantity(product_id, _parse_quantity(request.form.get("quantity")))
            flash("Cart updated.", "success")
        elif action == "remove":
            cart.remove(product_id)
            flash("Item removed.", "success")
        return redirect(url_for("storefront.cart_view"))

    lines, total = cart.lines()
    return render_template("storefront/cart.html", lines=lines, total=total)


@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    lines, total = cart.lines()
    if not lines:
        flash("Your cart is empty.", "info")
        return redirect(url_for("storefront.cart_view"))

    form = CheckoutForm()
    if form.validate_on_submit():
        order = _place_order(form)
        if order is not None:
            session[PLACED_ORDERS_KEY] = (session.get(PLACED_ORDERS_KEY) or [])[-19:] + [order.id]
            session.pop("checkout_ref", None)
            session.pop(CHECKOUT_QR_KEY, None)
            return redirect(url_for("storefront.order_confirmation", order_id=order.id))
        lines, total = cart.lines()
    return _render_checkout(form, lines, total)


@bp.post("/checkout/payment-status")
def checkout_payment_status():
    """One manual check of the KHQR on screen. The md5 comes from the session, never the browser."""
    lines, total = cart.lines()
    if not lines:
        flash("Your cart is empty.", "info")
        return redirect(url_for("storefront.cart_view"))
    try:
        payment = check_payment(payload_md5(_checkout_payload(total)))
    except KHQRConfigError as exc:
        payment = ("error", str(exc))
    return _render_checkout(CheckoutForm(formdata=None), lines, total, payment=payment)


def _checkout_reference():
    return session.setdefault("checkout_ref", secrets.token_hex(5).upper())


def _checkout_payload(total):
    """The KHQR string for this cart total, reused until the total changes.

    create_qr stamps the creation time into the payload, so rebuilding it would change the md5
    and the code the shopper already scanned. The signed session keeps the one we issued.
    """
    reference = _checkout_reference()
    amount = str(Decimal(total).quantize(Decimal("0.01")))
    cached = session.get(CHECKOUT_QR_KEY) or {}
    if (cached.get("amount") == amount and cached.get("ref") == reference
            and time.time() - cached.get("issued", 0) < CHECKOUT_QR_MAX_AGE):
        return cached["payload"]
    payload = build_payload(total, reference)
    session[CHECKOUT_QR_KEY] = {"amount": amount, "ref": reference, "issued": time.time(), "payload": payload}
    return payload


def _render_checkout(form, lines, total, payment=None):
    qr_image, qr_error = None, None
    try:
        qr_image = data_uri(_checkout_payload(total))
    except KHQRConfigError as exc:
        qr_error = str(exc)
    return render_template(
        "storefront/checkout.html", form=form, lines=lines, total=total,
        qr_image=qr_image, qr_error=qr_error, reference=_checkout_reference(), payment=payment,
    )


def _place_order(form):
    """Validate stock and write order, lines and stock decrement in one transaction."""
    qty_by_id = cart.quantities()
    try:
        products = db.session.execute(
            db.select(Product).where(Product.id.in_(qty_by_id)).with_for_update()
        ).scalars().all()
        by_id = {p.id: p for p in products}

        problems = []
        for pid, qty in qty_by_id.items():
            product = by_id.get(pid)
            if product is None or not product.is_active:
                problems.append("An item in your cart is no longer available and was removed.")
                cart.remove(pid)
            elif product.stock < qty:
                problems.append(f"Only {product.stock} of {product.name} left in stock.")
        if problems or not qty_by_id:
            db.session.rollback()
            for message in problems or ["Your cart is empty."]:
                flash(message, "error")
            return None

        order = Order(
            customer_name=form.full_name.data.strip(),
            email=form.email.data.strip(),
            phone=form.phone.data.strip(),
            address=form.address.data.strip(),
        )
        total = Decimal("0.00")
        for pid, qty in qty_by_id.items():
            product = by_id[pid]
            subtotal = product.price * qty
            total += subtotal
            order.items.append(OrderItem(
                product_id=product.id, product_name=product.name,
                quantity=qty, unit_price=product.price, subtotal=subtotal,
            ))
            product.stock -= qty
        order.total = total
        try:
            order.khqr_payload = _checkout_payload(total)
        except KHQRConfigError:
            order.khqr_payload = None
        db.session.add(order)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    cart.clear()
    return order


@bp.get("/order/<int:order_id>")
def order_confirmation(order_id):
    # Guests have no accounts; only the browser that placed the order may view it.
    if order_id not in (session.get(PLACED_ORDERS_KEY) or []):
        abort(404)
    order = db.session.get(Order, order_id) or abort(404)
    qr_image = None
    if order.khqr_payload:
        try:
            qr_image = data_uri(order.khqr_payload)
        except Exception:  # noqa: BLE001 - the confirmation still renders without the code
            qr_image = None
    return render_template("storefront/order.html", order=order, qr_image=qr_image)
