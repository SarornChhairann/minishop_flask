from flask import Blueprint

bp = Blueprint(
    "storefront",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/assets/storefront",
)

from . import routes  # noqa: E402,F401
