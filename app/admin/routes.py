import hmac

from flask import abort, current_app, flash, redirect, render_template, request, session, url_for

from ..extensions import db
from ..forms import LoginForm, ProductForm
from ..models import Order, OrderItem, Product
from ..services import images
from . import bp

SESSION_KEY = "admin_user"
OPEN_ENDPOINTS = {"admin.login", "admin.static"}


@bp.before_request
def require_login():
    if request.endpoint in OPEN_ENDPOINTS:
        return None
    if not session.get(SESSION_KEY):
        return redirect(url_for("admin.login", next=request.full_path.rstrip("?")))
    return None


def _credentials_match(username, password):
    expected_user = current_app.config.get("ADMIN_USERNAME", "")
    expected_pass = current_app.config.get("ADMIN_PASSWORD", "")
    if not expected_pass:
        return False
    user_ok = hmac.compare_digest(username.encode(), expected_user.encode())
    pass_ok = hmac.compare_digest(password.encode(), expected_pass.encode())
    return user_ok and pass_ok


@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if _credentials_match(form.username.data, form.password.data):
            session.clear()
            session[SESSION_KEY] = form.username.data
            target = request.args.get("next", "")
            if not (target.startswith("/admin") and not target.startswith("//")):
                target = url_for("admin.products")
            return redirect(target)
        flash("Wrong username or password.", "error")
    if not current_app.config.get("ADMIN_PASSWORD"):
        flash("ADMIN_PASSWORD is not set, so admin login is disabled.", "error")
    return render_template("admin/login.html", form=form)


@bp.post("/logout")
def logout():
    session.pop(SESSION_KEY, None)
    return redirect(url_for("admin.login"))


@bp.get("/")
def index():
    return redirect(url_for("admin.products"))


@bp.get("/products")
def products():
    rows = db.session.execute(db.select(Product).order_by(Product.id.desc())).scalars().all()
    return render_template("admin/products.html", products=rows)


@bp.route("/products/new", methods=["GET", "POST"])
def product_new():
    form = ProductForm()
    if request.method == "GET":
        form.stock.data = 0
    if form.validate_on_submit():
        try:
            original_url, thumb_url = images.save_upload(form.image.data)
        except images.ImageError as exc:
            form.image.errors.append(str(exc))
        else:
            product = Product(image_original_url=original_url, image_thumb_url=thumb_url)
            _fill(product, form)
            db.session.add(product)
            db.session.commit()
            flash(f"Created {product.name}.", "success")
            return redirect(url_for("admin.products"))
    return render_template("admin/product_form.html", form=form, product=None)


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
def product_edit(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    form = ProductForm(obj=product)
    if form.validate_on_submit():
        old_urls = None
        upload = form.image.data
        if upload and getattr(upload, "filename", ""):
            try:
                # Upload the new pair first so a failure leaves the product on its old images.
                new_original, new_thumb = images.save_upload(upload)
            except images.ImageError as exc:
                form.image.errors.append(str(exc))
                return render_template("admin/product_form.html", form=form, product=product)
            old_urls = (product.image_original_url, product.image_thumb_url)
            product.image_original_url, product.image_thumb_url = new_original, new_thumb
        _fill(product, form)
        db.session.commit()
        if old_urls:
            images.delete_urls(*old_urls)
        flash(f"Saved {product.name}.", "success")
        return redirect(url_for("admin.products"))
    return render_template("admin/product_form.html", form=form, product=product)


@bp.post("/products/<int:product_id>/delete")
def product_delete(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    urls = (product.image_original_url, product.image_thumb_url)
    name = product.name
    # Keep order history: detach line items instead of relying on database-specific ON DELETE.
    db.session.execute(
        db.update(OrderItem).where(OrderItem.product_id == product.id).values(product_id=None)
    )
    db.session.delete(product)
    db.session.commit()
    images.delete_urls(*urls)
    flash(f"Deleted {name}.", "success")
    return redirect(url_for("admin.products"))


@bp.get("/orders")
def orders():
    rows = db.session.execute(db.select(Order).order_by(Order.created_at.desc(), Order.id.desc())).scalars().all()
    return render_template("admin/orders.html", orders=rows)


@bp.get("/orders/<int:order_id>")
def order_detail(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    return render_template("admin/order_detail.html", order=order)


def _fill(product, form):
    product.name = form.name.data.strip()
    product.description = form.description.data.strip()
    product.price = form.price.data
    product.stock = form.stock.data
    product.status = form.status.data
