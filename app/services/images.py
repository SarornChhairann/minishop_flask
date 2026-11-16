"""Pillow pipeline plus storage.

Every upload becomes a compressed original and a thumbnail (both JPEG). The raw
upload is never stored. STORAGE_BACKEND=local writes under static/uploads for
development; STORAGE_BACKEND=s3 sends the same bytes to any S3-compatible host
(Cloudflare R2 by default), because Vercel's disk does not persist.
"""
import io
import os
import uuid

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 5 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ORIGINAL_EDGE, ORIGINAL_QUALITY = 1600, 82
THUMB_EDGE, THUMB_QUALITY = 480, 75


class ImageError(ValueError):
    pass


def _to_rgb(img):
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.getchannel("A"))
        return background
    return img.convert("RGB")


def _jpeg(img, quality):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def process_image(data):
    """Return (original_jpeg_bytes, thumbnail_jpeg_bytes) or raise ImageError."""
    if not data:
        raise ImageError("Choose an image file.")
    if len(data) > MAX_BYTES:
        raise ImageError("Images must be 5 MB or smaller.")
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageError("That file is not a readable image. Use JPEG, PNG or WEBP.")
    if fmt not in ALLOWED_FORMATS:
        raise ImageError("Use a JPEG, PNG or WEBP image.")

    img = _to_rgb(img)
    img.thumbnail((ORIGINAL_EDGE, ORIGINAL_EDGE), Image.LANCZOS)
    original = _jpeg(img, ORIGINAL_QUALITY)
    thumb_img = img.copy()
    thumb_img.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.LANCZOS)
    return original, _jpeg(thumb_img, THUMB_QUALITY)


def read_upload(file_storage):
    if file_storage is None or not file_storage.filename:
        raise ImageError("Choose an image file.")
    data = file_storage.stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ImageError("Images must be 5 MB or smaller.")
    return data


# --- storage -----------------------------------------------------------------

def _backend():
    return current_app.config.get("STORAGE_BACKEND", "local")


def _local_dir():
    return current_app.config.get("LOCAL_UPLOAD_DIR") or os.path.join(
        current_app.static_folder, "uploads"
    )


def _local_url_prefix():
    return f"{current_app.static_url_path}/uploads/"


def _s3_client():
    import boto3
    from botocore.config import Config

    cfg = current_app.config
    # Neon Object Storage is S3-compatible and requires path-style addressing.
    return boto3.client(
        "s3",
        endpoint_url=cfg["S3_ENDPOINT_URL"] or None,
        aws_access_key_id=cfg["S3_ACCESS_KEY_ID"] or None,
        aws_secret_access_key=cfg["S3_SECRET_ACCESS_KEY"] or None,
        region_name=cfg.get("S3_REGION") or "auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _put(key, data):
    if _backend() == "s3":
        cfg = current_app.config
        _s3_client().put_object(
            Bucket=cfg["S3_BUCKET"],
            Key=key,
            Body=data,
            ContentType="image/jpeg",
            CacheControl="public, max-age=31536000, immutable",
        )
        return f"{cfg['S3_PUBLIC_BASE_URL']}/{key}"
    path = os.path.join(_local_dir(), key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    # Plain path rather than url_for: seeding runs from the CLI with no request context.
    return f"{_local_url_prefix()}{key}"


def store_pair(original, thumb):
    """Store both JPEGs under fresh keys and return (original_url, thumb_url)."""
    name = f"{uuid.uuid4().hex}.jpg"
    return _put(f"original/{name}", original), _put(f"thumb/{name}", thumb)


def save_upload(file_storage):
    return store_pair(*process_image(read_upload(file_storage)))


def delete_urls(*urls):
    """Best-effort removal of stored objects; failures never raise."""
    for url in urls:
        if not url:
            continue
        try:
            if _backend() == "s3":
                base = current_app.config["S3_PUBLIC_BASE_URL"] + "/"
                if url.startswith(base):
                    _s3_client().delete_object(
                        Bucket=current_app.config["S3_BUCKET"], Key=url[len(base):]
                    )
            else:
                prefix = _local_url_prefix()
                if url.startswith(prefix):
                    key = url[len(prefix):]
                    if ".." not in key:
                        os.remove(os.path.join(_local_dir(), key))
        except Exception:  # noqa: BLE001 - storage cleanup must not break the request
            current_app.logger.warning("Could not delete stored image %s", url)
