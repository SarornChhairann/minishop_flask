# Loom

Loom is a clothes shop built with Flask, styled as a warm print catalogue. Guests browse, add to a cart and check out with a Bakong KHQR code. An admin site at `/admin` manages products and order history.

- Storefront: `/`, `/product/<id>`, `/cart`, `/checkout`, `/order/<id>`
- Admin: `/admin/login`, `/admin/products`, `/admin/products/new`, `/admin/products/<id>/edit`, `/admin/orders`, `/admin/orders/<id>`

## Run locally

Requires Python 3.10+ (Vercel uses 3.12).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit it; leave DATABASE_URL empty to use local.db (SQLite)
flask init-db               # creates tables
flask seed                  # 7 starter products; `flask seed --force` replaces them
flask run                   # http://127.0.0.1:5000
```

Sign in at `/admin/login` with `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env`. Admin login is disabled while `ADMIN_PASSWORD` is empty.

Tests use in-memory SQLite and need no cloud credentials:

```bash
pytest
pytest tests/test_checkout.py::test_checkout_refuses_oversell
```

## Environment variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Signs the session (cart and admin login). |
| `DATABASE_URL` | Neon Postgres **pooler** connection string with `sslmode=require`. Empty means `local.db`. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | The single admin login. |
| `SHOP_NAME`, `SHOP_TAGLINE` | Optional overrides for the shop identity. |
| `STORAGE_BACKEND` | `local` (default) or `s3`. |
| `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_PUBLIC_BASE_URL` | S3-compatible storage, used when `STORAGE_BACKEND=s3`. |
| `BAKONG_ACCOUNT_ID`, `MERCHANT_NAME`, `MERCHANT_CITY` | KHQR merchant details shown at checkout. |

## Images

Every upload is checked with Pillow (JPEG, PNG or WEBP, up to 5 MB) and converted into two JPEGs: an original capped at 1600px and a 480px thumbnail. The raw upload is never stored. The home grid and cart use the thumbnail. The product page uses the original.

`STORAGE_BACKEND=local` saves the files under `app/static/uploads/` and needs no cloud account. Vercel's filesystem is read-only and does not persist, so production must use `STORAGE_BACKEND=s3`. Cloudflare R2 works out of the box:

1. Create an R2 bucket and enable its public `r2.dev` URL. Put that URL in `S3_PUBLIC_BASE_URL`, without a trailing slash.
2. Create an R2 API token with object read and write access. Put its keys in `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY`.
3. Set `S3_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com`.

Any other S3-compatible host works by changing the same variables.

## KHQR

Checkout generates a dynamic KHQR for the cart total in USD with `bakong-khqr`. Generation happens offline and needs no Bakong API token. The order is saved when the guest submits the form. Payment status is not checked.

## Deploy to Vercel

1. Create a Vercel project with this folder (`chhairann/`) as its root directory.
2. Add the environment variables above. Use `STORAGE_BACKEND=s3` and the Neon pooler URL.
3. Deploy. `vercel.json` routes every request to `wsgi.py`.
4. Create the tables and seed once from your machine, pointing at the production services:
   `DATABASE_URL=... STORAGE_BACKEND=s3 S3_...=... flask init-db && flask seed`
