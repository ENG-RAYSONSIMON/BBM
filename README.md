# Beauty Business Manager (BBM)

Multi-tenant SaaS for Tanzanian cosmetics/beauty retailers. Each business
(tenant) manages its own products, stock, sales, purchases, expenses and
profit reports.

- Requirements: `docs/BBM_SRS_Summary_Draft.pdf`
- Architecture rules and working conventions: `CLAUDE.md`
- What Phase 1 actually built: `docs/PHASE_1_SUMMARY.md`

---

## Current state / next step

**Done: Phase 1, Identity & Tenant Core (FR-1 to FR-5).** Backend only.
- Email/password registration creates User + Business + Owner and Admin roles
  (with default permissions) + owner membership + settings in a single atomic
  transaction.
- JWT login (20 min access / 7 day refresh, rotating and blacklisted). The token
  carries a signed `business_id` claim.
- Central tenant scoping: `core.models.TenantModel` +
  `core.managers.TenantManager`, activated only by
  `core.authentication.TenantJWTAuthentication`.
- Password reset (FR-4): time-limited, single-use, hashed tokens sent by email
  (console backend for now). The request endpoint answers the same way whether
  or not the account exists. A completed reset ends all sessions.
- Table-driven permissions (FR-5): `Role → RolePermission → Permission`.
  `core.permissions.HasTenantPermission` is a default permission class; every
  authenticated view declares `required_permissions`. Owner and Admin differ
  only by table rows, so a new role (e.g. Cashier) needs no code change.
- OpenAPI schema with Swagger UI and ReDoc (development only; see §6).
- 53 tests, all passing. The FR-4/FR-5 and OpenAPI changes are not committed yet.

**Open from Phase 1:** see §6–§8 of `docs/PHASE_1_SUMMARY.md`. The main items:
- Rate limiting exists only on the password-reset endpoints; login, register
  and refresh are unthrottled (NFR-3). Throttle counters use the in-process
  cache, not Redis.
- No API for managing staff, roles or grants yet (Django admin only).
- Access tokens stay valid for up to 20 minutes after a password reset.

**Next: Phase 2, Catalog & Inventory (FR-6 to FR-10).**

| FR | Requirement |
|---|---|
| FR-6 | Product CRUD with category, brand, supplier, batch, expiry — per tenant |
| FR-7 | Every stock change (sale, purchase, damage, adjustment, transfer, expiry) is a `stock_movements` row |
| FR-8 | Current stock = sum over `stock_movements`; never a directly edited quantity |
| FR-9 | Low-stock and expiry (7/30/60-day, expired) views from live queries, filterable by category/brand/supplier |
| FR-10 | Validate uploaded product images by type and size before storage |

Rules to follow when starting Phase 2:
- Every new tenant-owned model subclasses `core.models.TenantModel`. Don't add
  a `business` field by hand, and never accept `business_id` from the client.
- Use `Model.objects` in views and services. `all_objects` is only for trusted
  system code.
- `bulk_create()` skips `TenantModel.save()`, so set `business` explicitly there.
- Every authenticated view must declare `required_permissions` (a tuple, or a
  dict of HTTP method → tuple); an undeclared view raises
  `ImproperlyConfigured`. New codenames go in `accounts/rbac.py` (`PERMISSIONS`
  and `DEFAULT_ROLE_PERMISSIONS`) plus a data migration that inserts them and
  grants them to existing businesses' roles (see `0003_seed_permissions`).
  Never check role names in views or services.
- Give every new endpoint `@extend_schema` with `tags`, a `summary` and its
  real `responses`. `accounts.tests.test_schema` fails on any schema warning
  or error.
- Every detail/update/delete endpoint needs a cross-tenant test: tenant B
  requests tenant A's UUID and must get 404 (NFR-7).
- `stock_movements` needs a `(business, created_at)` index (NFR-8). Stock
  thresholds come from `BusinessSettings.low_stock_threshold` and
  `expiry_warning_days`.
- Plan first, get approval, then implement (see `CLAUDE.md`).

---

## Prerequisites

- Docker Engine with the Compose v2 plugin (`docker compose`, not
  `docker-compose`)
- Git
- Optional: `curl` and `jq` for trying the API from a shell

No local Python is needed; everything runs in containers. (`backend/venv/` is
gitignored if you keep one for editor tooling.)

## Stack in this repo today

| Service | Image / build | Host port |
|---|---|---|
| `db` | `postgres:15` (named volume `pgdata`) | `5433` → 5432 |
| `redis` | `redis:7` (nothing uses it yet) | `6379` |
| `backend` | `./backend` (Python 3.12, Django 6.1, DRF, SimpleJWT, drf-spectacular), `runserver` with `./backend` mounted at `/app` | `8000` |

`frontend` and `nginx` aren't in `docker-compose.yml` yet.

---

## 1. Environment files

There are two env files, both gitignored. There's no `.env.example` yet, so
create them by hand.

**`./.env`**: read by `docker compose` to configure the `db` container.

```dotenv
POSTGRES_DB=REPLACE_ME          # e.g. bbm
POSTGRES_USER=REPLACE_ME
POSTGRES_PASSWORD=REPLACE_ME
```

**`./backend/.env`**: read by Django (`django-environ`), and also passed to the
backend container via `env_file`.

```dotenv
DJANGO_SECRET_KEY=REPLACE_ME
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://<POSTGRES_USER>:<POSTGRES_PASSWORD>@db:5432/<POSTGRES_DB>
CORS_ALLOWED_ORIGINS=http://localhost:5173

# Optional (defaults shown). None of these are secrets.
# FRONTEND_URL=http://localhost:5173        # base of the password-reset link
# PASSWORD_RESET_TIMEOUT=1800               # reset token lifetime, seconds
# PASSWORD_RESET_THROTTLE_RATE=5/hour       # per IP, both reset endpoints
# DEFAULT_FROM_EMAIL=no-reply@bbm.local
```

Notes:
- Inside Compose the database host is **`db:5432`**. Port `5433` is only for
  tools running on your machine (psql, DBeaver).
- If the password contains URL-special characters (`@ : / # ?`), percent-encode
  them in `DATABASE_URL` (e.g. `@` → `%40`).
- Email uses Django's console backend (`MAILERS` in `config/settings.py`), so
  password-reset emails print in `docker compose logs backend`. When real SMTP
  is added, its credentials go in `backend/.env` as `REPLACE_ME` placeholders.
- To generate a secret key:
  `docker compose run --rm backend python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`

## 2. Bring the stack up

```bash
docker compose up -d --build        # db, redis, backend
docker compose ps                   # all three should be "Up"
docker compose logs -f backend      # watch runserver; Ctrl+C to stop following
```

`depends_on` has no healthcheck, so on a cold start the backend can come up
before Postgres accepts connections. If the backend logs show a connection
error, run `docker compose restart backend`.

To stop:

```bash
docker compose down                 # keeps the database volume
docker compose down -v              # also DELETES the pgdata volume (all data)
```

## 3. Migrations and an admin user

```bash
docker compose exec backend python manage.py migrate          # accounts 0001–0003
docker compose exec backend python manage.py showmigrations
docker compose exec backend python manage.py createsuperuser   # asks for email, not username
```

After changing models:

```bash
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
```

Django admin is at http://localhost:8000/admin/. Tenant models (Role, UserRole,
RolePermission, BusinessSettings) can't be created there; tenant rows are
created by services. Existing grants can be edited or deleted in admin, and
changes take effect on the next request. The Permission catalog is read-only
(it's maintained through `accounts/rbac.py` and data migrations).

Migration `0003_seed_permissions` also backfills businesses that existed
before it: each gets an Admin role, and its Owner and Admin roles get their
default permissions.

## 4. Run the tests

```bash
docker compose exec backend python manage.py test            # whole suite (53 tests)
docker compose exec backend python manage.py test -v 2       # list each test
docker compose exec backend python manage.py test core       # tenant-scoping tests
docker compose exec backend python manage.py test accounts   # registration, auth, password reset, permissions
docker compose exec backend python manage.py test accounts.tests.test_password_reset
docker compose exec backend python manage.py test accounts.tests.test_permissions
docker compose exec backend python manage.py test accounts.tests.test_schema
docker compose exec backend python manage.py check
```

If the backend container isn't running, replace `exec backend` with
`run --rm backend`. Tests create and then drop a `test_<POSTGRES_DB>` database,
so the DB user needs `CREATEDB` (the default `postgres` image user has it).

## 5. Hit the API

Base URL: `http://localhost:8000/api/v1/`

```bash
# Register (201): creates user + business, returns tokens
curl -s -X POST localhost:8000/api/v1/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.com","password":"Str0ng-Passw0rd!","business_name":"Glow Cosmetics"}' | jq

# Log in (200). Add "business_id" if the user belongs to several businesses.
ACCESS=$(curl -s -X POST localhost:8000/api/v1/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.com","password":"Str0ng-Passw0rd!"}' | jq -r .access)

# Who am I / which business is active
curl -s localhost:8000/api/v1/auth/me/ -H "Authorization: Bearer $ACCESS" | jq

# Refresh (rotates; the old refresh token stops working)
curl -s -X POST localhost:8000/api/v1/auth/refresh/ \
  -H 'Content-Type: application/json' -d '{"refresh":"<refresh token>"}' | jq

# Logout (204; needs access token + your own refresh token)
curl -s -X POST localhost:8000/api/v1/auth/logout/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"refresh":"<refresh token>"}' -w '%{http_code}\n'

# Business settings: GET needs settings.view (Owner, Admin), PATCH needs settings.manage (Owner)
curl -s localhost:8000/api/v1/settings/ -H "Authorization: Bearer $ACCESS" | jq
curl -s -X PATCH localhost:8000/api/v1/settings/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"low_stock_threshold":10,"tax_rate":"18.00"}' | jq

# Password reset, step 1 (always 202, whether or not the email exists).
# The link prints in `docker compose logs backend`: .../reset-password#token=<token>
curl -s -X POST localhost:8000/api/v1/auth/password-reset/ \
  -H 'Content-Type: application/json' -d '{"email":"owner@example.com"}' | jq

# Password reset, step 2 (204; 400 if the token is invalid, used or expired)
curl -s -X POST localhost:8000/api/v1/auth/password-reset/confirm/ \
  -H 'Content-Type: application/json' \
  -d '{"token":"<token>","new_password":"An0ther-Str0ng-One!"}' -w '%{http_code}\n'
```

| Method | Path | Auth | Permission |
|---|---|---|---|
| POST | `/api/v1/auth/register/` | none | — |
| POST | `/api/v1/auth/login/` | none | — |
| POST | `/api/v1/auth/refresh/` | none | — |
| POST | `/api/v1/auth/logout/` | Bearer | any member |
| GET | `/api/v1/auth/me/` | Bearer | any member (also returns your `permissions`) |
| POST | `/api/v1/auth/password-reset/` | none, 5/hour per IP | — |
| POST | `/api/v1/auth/password-reset/confirm/` | none, 5/hour per IP | — |
| GET | `/api/v1/settings/` | Bearer | `settings.view` |
| PATCH | `/api/v1/settings/` | Bearer | `settings.manage` |

A missing permission returns **403**. Request and response details:
`docs/PHASE_1_SUMMARY.md` §3 (auth), §7 (password reset), §8 (permissions).

## 6. API docs (OpenAPI)

Generated by `drf-spectacular`. **Routed only when `DEBUG=True`**; with
`DEBUG=False` these URLs return 404.

| URL | What |
|---|---|
| http://localhost:8000/api/docs/ | Swagger UI (try requests in the browser) |
| http://localhost:8000/api/redoc/ | ReDoc (read-only reference) |
| http://localhost:8000/api/schema/ | Raw OpenAPI 3 schema (YAML; `?format=json` for JSON) |

No login is needed to open them. To call protected endpoints from Swagger UI:
1. Run `POST /api/v1/auth/login/` (or register) with **Try it out** and copy
   `access` from the response.
2. Click **Authorize**, paste the token (without the `Bearer ` prefix), then
   **Authorize**. The token is kept across page reloads.
3. It expires after 20 minutes; get a new one from `/auth/refresh/`.

Operations are grouped by tag (`auth`, `password reset`, `settings`). Each
protected operation's description shows the permission it needs
(e.g. **Requires permission:** `settings.manage`), also exposed as the
`x-required-permissions` field. This comes from the view's
`required_permissions`, so it always matches what is enforced.

Swagger UI and ReDoc load their JavaScript/CSS from the jsDelivr CDN, so the
browser needs internet access.

Export and validate the schema (works in any environment, e.g. for frontend
client generation):

```bash
docker compose exec backend python manage.py spectacular --validate --fail-on-warn --file schema.yml
```

---

## Repo layout

```
BBM/
├── docker-compose.yml
├── .env                      # compose vars (gitignored)
├── docs/
│   ├── BBM_SRS_Summary_Draft.pdf
│   └── PHASE_1_SUMMARY.md
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    ├── .env                  # Django vars (gitignored)
    ├── config/               # settings, root urls (API docs routes when DEBUG)
    ├── core/                 # tenancy: TenantModel, TenantManager, tenant context,
    │                         #   TenantJWTAuthentication, HasTenantPermission,
    │                         #   OpenAPI schema hooks (schema.py), middleware, admin base
    └── accounts/             # User, Business, Role, UserRole, BusinessSettings,
                              #   Permission, RolePermission, PasswordResetToken;
                              #   rbac.py (permission catalog + role defaults);
                              #   register/login/refresh/logout/me, password reset,
                              #   settings
```
