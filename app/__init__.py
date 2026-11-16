from flask import Flask, flash, redirect, render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import csrf, db


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)

    # Vercel terminates TLS in front of the function; trust its forwarded scheme/host
    # so url_for(..., _external=True) builds https share links.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    db.init_app(app)
    csrf.init_app(app)

    from . import models  # noqa: F401  (register tables)
    from .admin import bp as admin_bp
    from .commands import register_commands
    from .storefront import bp as storefront_bp

    app.register_blueprint(storefront_bp)
    app.register_blueprint(admin_bp)
    register_commands(app)

    @app.template_filter("usd")
    def usd(value):
        return f"${value:,.2f}"

    @app.errorhandler(404)
    def not_found(_):
        return render_template("storefront/error.html", title="Not found",
                               message="That page or product does not exist."), 404

    @app.errorhandler(413)
    def too_large(_):
        flash("Images must be 5 MB or smaller.", "error")
        return redirect(request.url)

    @app.errorhandler(CSRFError)
    def csrf_error(_):
        return render_template("storefront/error.html", title="Form expired",
                               message="Your form expired. Go back, reload the page and try again."), 400

    return app
