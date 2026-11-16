from flask import Blueprint

bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates",
    static_folder="static",
    static_url_path="/assets",
)

from . import routes  # noqa: E402,F401
