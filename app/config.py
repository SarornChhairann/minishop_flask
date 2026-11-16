import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_SHOP_NAME = "Psaa"
DEFAULT_SHOP_TAGLINE = "Everyday clothes, cut simply."


def normalize_database_url(url):
    """Neon hands out postgres:// URLs. SQLAlchemy needs the psycopg 3 driver name."""
    url = url.strip().strip('"').strip("'")
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        # Local fallback so the app runs without Neon. Vercel always sets DATABASE_URL.
        return f"sqlite:///{BASE_DIR / 'local.db'}"
    # Application traffic uses the pooled host. Schema changes use the direct URL.
    return normalize_database_url(url)


def direct_database_url():
    """Direct (non-pooler) URL for init-db. Pooled connections drop session state."""
    url = os.environ.get("DATABASE_URL_UNPOOLED", "").strip()
    return normalize_database_url(url) if url else None


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    SQLALCHEMY_DATABASE_URI = _database_url()
    # Vercel runs many short-lived interpreters: borrow one pooled Neon connection per request, then drop it.
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"poolclass": NullPool, "pool_pre_ping": True}
        if SQLALCHEMY_DATABASE_URI.startswith("postgresql")
        else {}
    )

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("VERCEL") == "1"

    SHOP_NAME = os.environ.get("SHOP_NAME") or DEFAULT_SHOP_NAME
    SHOP_TAGLINE = os.environ.get("SHOP_TAGLINE") or DEFAULT_SHOP_TAGLINE

    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

    # Neon object storage injects AWS_*. Those win over the older S3_* names so a
    # pulled .env does not keep sending uploads to a placeholder R2 host.
    _neon_endpoint = os.environ.get("AWS_ENDPOINT_URL_S3", "").strip()
    if _neon_endpoint:
        STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "s3").lower()
        S3_ENDPOINT_URL = _neon_endpoint
        S3_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
        S3_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        S3_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
        S3_BUCKET = os.environ.get("S3_BUCKET", "").strip() or "assets"
        S3_PUBLIC_BASE_URL = (
            os.environ.get("S3_PUBLIC_BASE_URL", "").strip()
            or f"{_neon_endpoint.rstrip('/')}/{S3_BUCKET}"
        ).rstrip("/")
    else:
        STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").lower()
        S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "")
        S3_BUCKET = os.environ.get("S3_BUCKET", "")
        S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID", "")
        S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY", "")
        S3_REGION = os.environ.get("S3_REGION", "auto")
        S3_PUBLIC_BASE_URL = os.environ.get("S3_PUBLIC_BASE_URL", "").rstrip("/")
    LOCAL_UPLOAD_DIR = None  # defaults to app/static/uploads

    BAKONG_ACCOUNT_ID = os.environ.get("BAKONG_ACCOUNT_ID", "")
    MERCHANT_NAME = os.environ.get("MERCHANT_NAME", "")
    MERCHANT_CITY = os.environ.get("MERCHANT_CITY", "Phnom Penh")
    BAKONG_PROXY_URL = os.environ.get("BAKONG_PROXY_URL", "").strip().rstrip("/")
    BAKONG_PROXY_SECRET = os.environ.get("BAKONG_PROXY_SECRET", "").strip()
