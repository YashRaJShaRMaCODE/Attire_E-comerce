# Govind Attire Store

Django storefront prototype with product browsing, customer accounts, a database-backed bag, saved addresses, and order requests.

## Current checkout limits

Checkout records an order request and reserves available stock. It does **not** collect payment, calculate delivery charges or taxes, send order emails, or handle refunds and cancellations. Do not accept live orders until those business flows and a supported production database are configured.

The project uses SQLite for local development. SQLite does not provide the row-level locks used by the order flow. Configure PostgreSQL before handling concurrent live orders; set `DJANGO_DB_ENGINE=django.db.backends.postgresql` and provide `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT`. Connections require TLS by default. See Django’s [`select_for_update()` documentation](https://docs.djangoproject.com/en/6.1/ref/models/querysets/#select-for-update).

## Local setup

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, generate a local key, and set `DJANGO_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

The example enables `DJANGO_DEBUG` for local use. Never use that setting or a development secret in production. Then run:

```bash
python manage.py migrate
python manage.py check
python manage.py test home
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. Add categories and products in `/admin/`. Product image URLs should point to assets you own or are licensed to use; replace the sample hero photo before launch.

## Production setup

- Use a generated `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, and exact `DJANGO_ALLOWED_HOSTS` values.
- Run `python manage.py collectstatic --noinput` and serve the collected files from `STATIC_ROOT`.
- Configure HTTPS at the hosting proxy. Set `SECURE_SSL_REDIRECT=true` only when the proxy reports HTTPS to Django correctly; enable HSTS only after verifying the full domain and its subdomains use HTTPS.
- Configure PostgreSQL or MySQL, backups, monitoring, email delivery, and a payment provider before taking real orders.
- Review privacy, consumer-protection, tax, delivery, cancellation, and refund requirements for the target market.

## Main routes

- `/` and `/products/`: storefront and catalog
- `/products/<slug>/`: product detail
- `/cart/` and `/checkout/`: bag and order request
- `/my-account/`: account and recent orders
- `/admin/`: product and order management
