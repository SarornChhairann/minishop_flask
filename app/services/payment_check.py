"""One manual payment check through the Cambodia-hosted Bakong proxy. No polling."""
import httpx
from flask import current_app

TIMEOUT_SECONDS = 20


def check_payment(md5):
    """Return (status, message). Status is paid, unpaid, error or unconfigured."""
    cfg = current_app.config
    url, secret = cfg.get("BAKONG_PROXY_URL", ""), cfg.get("BAKONG_PROXY_SECRET", "")
    if not url or not secret:
        return "unconfigured", "Payment check is not configured for this shop."
    try:
        resp = httpx.post(f"{url}/v1/check", json={"md5": md5},
                          headers={"Authorization": f"Bearer {secret}"}, timeout=TIMEOUT_SECONDS)
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        current_app.logger.warning("Bakong proxy unreachable: %s", exc)
        return "error", "Could not reach the payment checker. Try again in a moment."
    status = body.get("status") if isinstance(body, dict) else None
    if status not in ("paid", "unpaid", "error"):
        return "error", f"Unexpected answer from the payment checker (HTTP {resp.status_code})."
    return status, body.get("message") or ""
