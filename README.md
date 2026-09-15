# Beauty Business Manager (BBM)

Multi-tenant SaaS for Tanzanian cosmetics/beauty retailers. Each business
(tenant) manages its own products, stock, sales, purchases, expenses and
profit reports.

- Requirements: `docs/BBM_SRS_Summary_Draft.pdf`
- Architecture rules and working conventions: `CLAUDE.md`
- What Phase 1 actually built: `docs/PHASE_1_SUMMARY.md`

---

## Current state / next step

**Done: Phase 1, Identity & Tenant Core (FR-1, FR-2, FR-3).** Backend only.
- Email/password registration creates User + Business + Owner role + membership
  + settings in a single atomic transaction.
- JWT login (20 min access / 7 day refresh, rotating and blacklisted). The token
  carries a signed `business_id` claim.
- Central tenant scoping: `core.models.TenantModel` +
  `core.managers.TenantManager`, activated only by
  `core.authentication.TenantJWTAuthentication`.
- 24 tests, all passing. **Nothing has been committed to git yet.**

**Open from Phase 1:** see §6 of `docs/PHASE_1_SUMMARY.md`. The main items:
- FR-4 (password reset) and FR-5 (table-driven permissions) are Phase 1 in the
  SRS but not built. Decide whether to finish them or explicitly defer them.
- OpenAPI docs aren't routed yet (see "API docs" below).
- No auth rate limiting (NFR-3).

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
```

Notes:
- Inside Compose the database host is **`db:5432`**. Port `5433` is only for
  tools running on your machine (psql, DBeaver).
- If the password contains URL-special characters (`@ : / # ?`), percent-encode
  them in `DATABASE_URL` (e.g. `@` → `%40`).
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
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py showmigrations
docker compose exec backend python manage.py createsuperuser   # asks for email, not username
```

After changing models:

```bash
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
```

Django admin is at http://localhost:8000/admin/. Tenant models (Role, UserRole,
BusinessSettings) are read-only for creation there; tenant rows are created by
services.

## 4. Run the tests

```bash
docker compose exec backend python manage.py test            # whole suite (24 tests)
docker compose exec backend python manage.py test -v 2       # list each test
docker compose exec backend python manage.py test core       # tenant-scoping tests
docker compose exec backend python manage.py test accounts   # registration + auth tests
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
```

| Method | Path | Auth |
|---|---|---|
| POST | `/api/v1/auth/register/` | none |
| POST | `/api/v1/auth/login/` | none |
| POST | `/api/v1/auth/refresh/` | none |
| POST | `/api/v1/auth/logout/` | Bearer |
| GET | `/api/v1/auth/me/` | Bearer |

Request and response details: `docs/PHASE_1_SUMMARY.md` §3.

## 6. API docs (OpenAPI)

**Not wired up yet.** `drf-spectacular` is installed and configured as the
schema class, but `config/urls.py` routes no schema or Swagger views, so there
is no docs URL today. Until it's wired, you can generate the schema file:

```bash
docker compose exec backend python manage.py spectacular --file schema.yml
```

This currently reports one error (`MeView` has no serializer, so it's left out
of the schema) and two warnings (Bearer auth isn't documented for
`TenantJWTAuthentication`). Fixing that is a small, separate task. The usual
wiring adds `SpectacularAPIView` at `/api/schema/` and
`SpectacularSwaggerView` at `/api/docs/`. Once that's done, the docs will be at
http://localhost:8000/api/docs/.

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
    ├── config/               # settings, root urls
    ├── core/                 # tenancy: TenantModel, TenantManager, tenant context,
    │                         #   TenantJWTAuthentication, middleware, admin base
    └── accounts/             # User, Business, Role, UserRole, BusinessSettings,
                              #   register/login/refresh/logout/me
```
