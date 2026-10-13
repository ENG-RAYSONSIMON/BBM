# Beauty Business Manager (BBM)

Multi-tenant SaaS for Tanzanian cosmetics/beauty retailers. Each business
(tenant) manages its own products, stock, sales, purchases, expenses and
profit reports.

- Requirements: `docs/BBM_SRS_Summary_Draft.pdf`
- Architecture rules and working conventions: `CLAUDE.md`
- What each phase built: `docs/PHASE_1_SUMMARY.md`, `docs/PHASE_2_SUMMARY.md`,
  `docs/PHASE_3_SUMMARY.md`

---

## Current state / next step

**Done: Phase 1, Identity & Tenant Core (FR-1 to FR-5)**, backend and frontend.
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
- Rate limiting (NFR-3) on register, login, refresh and password reset, with
  counters in Redis. System roles can't be renamed or deleted, and the Owner
  role's grants can't be removed.
- Frontend (`frontend/`, React + Vite): register, login (with a business picker
  for multi-business accounts), forgot/reset password, a dashboard with
  empty states, and business settings (editable with `settings.manage`).
- OpenAPI schema with Swagger UI and ReDoc (development only; see §6).
- 61 backend tests and 16 frontend tests, all passing.

**Done: Phase 2, Catalog & Inventory (FR-6 to FR-10)**, backend and frontend.
See `docs/PHASE_2_SUMMARY.md`.
- Categories, brands, suppliers and products (prices, SKU/barcode, reorder
  level, expiry tracking, archive), with validated product images.
- Stock is held per batch and is always the sum of the append-only
  `StockMovement` ledger. Manual adjustments (stock in, damage, expiry,
  corrections) until Phase 3 purchases and sales.
- Live low-stock and expiry (7/30/60-day, expired) views and dashboard counts.
- Pagination, search and filters on every list; NFR-7 cross-tenant tests on
  every Phase 2 endpoint.

**Done: Phase 3, The Money Path (FR-11 to FR-17)**, backend and frontend. See
`docs/PHASE_3_SUMMARY.md`.
- A sale is one atomic transaction: stock is checked and taken from the
  earliest-expiring batches (expired stock is never sold), price and cost are
  snapshotted, and the cash received is recorded with the change given.
- Selling on credit: a customer can pay part or nothing; the balance is tracked
  per sale and per customer, and repayments are recorded later.
- Voiding a sale returns its stock to the original batches and refunds the
  cash collected; nothing is deleted. Payments, like stock movements, are
  append-only.
- Sale screen (`/pos`), sales list and receipts, customers with what they owe.
- Purchases (FR-14): a draft is edited freely; receiving it writes `PURCHASE`
  movements into new or existing batches in one transaction and sets each
  product's cost price to what was paid.
- Expenses (FR-15) by category, with an optional photo or PDF receipt served
  only through the API.
- Net profit (FR-16) = gross profit − expenses for the period. The dashboard
  (FR-17) shows sales, gross and net profit, expenses, cash and credit for
  today, the last 7 days or this month.

**Languages: Kiswahili (default) and English.** A language button next to the
theme button switches the whole app, including server error messages. See §7.

**Open items:** `docs/PHASE_1_SUMMARY.md` §6–§8, `docs/PHASE_2_SUMMARY.md` and
`docs/PHASE_3_SUMMARY.md` "Known gaps" (e.g. no staff-management API yet;
media served by Django in dev only; cash is the only payment method).

**Next: Phase 4** (reports with CSV export FR-18, notifications FR-19, audit
log FR-20), unless Phase 3's known gaps come first.

Rules that still apply:
- Every new tenant-owned model subclasses `core.models.TenantModel`; never
  accept `business_id` from the client. Use `Model.objects` in views and
  services (`all_objects` only for trusted system code). `bulk_create()` skips
  `TenantModel.save()`.
- Foreign keys between tenant models call `check_same_business(...)` in
  `save()` (see `catalog/models.py`).
- Stock changes only through `inventory.services.record_movement()`.
- Every authenticated view declares `required_permissions`. New codenames go in
  `accounts/rbac.py` plus a data migration (copy the latest,
  `accounts/0006_phase3_purchases_expenses_permissions`).
- Every endpoint gets `@extend_schema`; `accounts.tests.test_schema` fails on
  any warning. Every detail endpoint gets a cross-tenant 404 test.
- No hard-coded user-visible text: `_()` on the backend (then `makemessages` /
  `compilemessages`, §7) and `t()` keys in both `en.ts` and `sw.ts` on the
  frontend.
- Plan first, get approval, then implement (see `CLAUDE.md`).

---

## Prerequisites

- Docker Engine with the Compose v2 plugin (`docker compose`, not
  `docker-compose`)
- Git
- Optional: `curl` and `jq` for trying the API from a shell

No local Python or Node is needed; everything runs in containers. (`backend/venv/`
is gitignored if you keep one for editor tooling.)

These host ports must be free: `5173` (frontend), `8000` (backend), `5433`
(Postgres) and `6379` (Redis).

## Stack in this repo today

| Service | Image / build | Host port |
|---|---|---|
| `db` | `postgres:15` (named volume `pgdata`) | `5433` → 5432 |
| `redis` | `redis:7` (throttle counters, via `REDIS_URL`) | `6379` |
| `backend` | `./backend` (Python 3.12, Django 6.1, DRF, SimpleJWT, drf-spectacular), `runserver` with `./backend` mounted at `/app` | `8000` |
| `frontend` | `node:24-alpine`, Vite dev server with `./frontend` mounted (`npm ci` on start) | `5173` |

The frontend's `node_modules` lives in the named volume `frontend_node_modules`,
not in `./frontend/node_modules` on your machine, so the Linux-built packages in
the container never mix with anything you install locally.

`nginx` isn't in `docker-compose.yml` yet.

---

## 1. Environment files

There are two env files, both gitignored. Copy the examples and fill in every
`REPLACE_ME`:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

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
REDIS_URL=redis://redis:6379/0               # throttle counters; LocMem if unset

# Optional (defaults shown). None of these are secrets.
# FRONTEND_URL=http://localhost:5173        # base of the password-reset link
# PASSWORD_RESET_TIMEOUT=1800               # reset token lifetime, seconds
# PASSWORD_RESET_THROTTLE_RATE=5/hour       # per IP, both reset endpoints
# LOGIN_THROTTLE_RATE=10/min                # per IP
# REGISTER_THROTTLE_RATE=5/hour             # per IP
# TOKEN_REFRESH_THROTTLE_RATE=30/min        # per IP
# DEFAULT_FROM_EMAIL=no-reply@bbm.local
# PRODUCT_IMAGE_MAX_BYTES=2097152           # product image upload limit
# EXPENSE_RECEIPT_MAX_BYTES=5242880         # expense receipt upload limit
# PRIVATE_MEDIA_ROOT=/app/private_media     # receipts; never served at /media/
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
- `CORS_ALLOWED_ORIGINS` must contain the exact origin the browser loads the
  frontend from (`http://localhost:5173`). If it doesn't match, login and every
  other API call fail with a CORS error in the browser console.

**Frontend: no env file needed under Docker.** `docker-compose.yml` sets
`VITE_API_URL=http://localhost:8000/api/v1` on the `frontend` service. The
browser calls that URL, so it uses the host port, not `backend:8000`.
`frontend/.env` (copied from `frontend/.env.example`) is only used if you run
`npm run dev` on your machine outside Docker.

## 2. Bring the stack up

### First run

1. Create and fill in the env files (§1).

2. Build and start all four services (db, redis, backend, frontend):

   ```bash
   docker compose up -d --build
   docker compose ps                   # db, redis, backend and frontend should all be "Up"
   ```

3. Wait for the frontend to be ready. The first start runs `npm ci` inside the
   container, which takes a minute or two; later starts are faster.

   ```bash
   docker compose logs -f frontend     # wait for "Local: http://localhost:5173/"; Ctrl+C to stop following
   docker compose logs -f backend      # runserver output, should say "Starting development server"
   ```

4. Create the database tables (first run, and after pulling new migrations):

   ```bash
   docker compose exec backend python manage.py migrate
   ```

5. Open **http://localhost:5173**, click **Register**, and create a business.
   You land on the dashboard as its Owner. From there, set up
   **Catalog** (categories, brands, suppliers), add **Products**, and bring
   stock in with **Purchases** (save a draft, then receive it) or an
   adjustment on a product's page. Sell from the **Sale screen** (`/pos`),
   record **Expenses**, and check **Inventory** for low-stock and expiry
   alerts and the dashboard for profit.

| URL | What |
|---|---|
| http://localhost:5173 | The app (React frontend) |
| http://localhost:8000/api/v1/ | REST API |
| http://localhost:8000/admin/ | Django admin (needs a superuser, §3) |
| http://localhost:8000/api/docs/ | Swagger UI (`DEBUG=True` only, §6) |

### Day to day

```bash
docker compose up -d                # start everything (no rebuild needed)
docker compose restart frontend     # restart one service
docker compose restart backend
docker compose logs -f backend frontend
```

`./backend` and `./frontend` are bind-mounted, so code changes hot-reload:
runserver restarts on Python changes and Vite updates the browser on frontend
changes. Rebuild the backend image (`docker compose up -d --build backend`)
only after changing `backend/requirements.txt` or `backend/Dockerfile` (the
image includes `gettext` for translations, §7).

After `frontend/package.json` or `package-lock.json` changes, run
`docker compose restart frontend`; `npm ci` runs on every start and reinstalls
from the lockfile. If the frontend still sees stale or broken packages, recreate
its dependency volume:

```bash
docker compose down
docker volume ls | grep frontend_node_modules   # name is prefixed with the project dir, e.g. bbm_
docker volume rm bbm_frontend_node_modules
docker compose up -d
```

### Stop

```bash
docker compose down                 # stops containers, keeps the volumes (data is kept)
docker compose down -v              # also DELETES the volumes: the database (all data)
                                    #   and the frontend node_modules
```

### Troubleshooting

- **Backend logs show a database connection error on a cold start.**
  `depends_on` has no healthcheck, so the backend can start before Postgres
  accepts connections. Run `docker compose restart backend`.
- **The browser console shows a CORS error, or login does nothing.** Check
  that `CORS_ALLOWED_ORIGINS` in `backend/.env` is `http://localhost:5173`, then
  `docker compose restart backend`.
- **API calls fail with "relation ... does not exist".** Migrations haven't
  been applied; run step 4.
- **http://localhost:5173 doesn't load.** `npm ci` may still be running or may
  have failed; check `docker compose logs frontend`.
- **"port is already allocated".** Another process uses 5173, 8000, 5433 or
  6379. Stop it, or change the left side of that port mapping in
  `docker-compose.yml`. If you change the backend port, also update
  `VITE_API_URL`.
- **Password-reset email.** It isn't sent; the link is printed in
  `docker compose logs backend`.

## 3. Migrations and an admin user

The first `migrate` is part of §2. Other useful commands:

```bash
docker compose exec backend python manage.py migrate          # accounts, catalog, inventory, …
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
docker compose exec backend python manage.py test            # whole suite (201 tests)
docker compose exec backend python manage.py test -v 2       # list each test
docker compose exec backend python manage.py test core       # tenant-scoping tests
docker compose exec backend python manage.py test accounts   # registration, auth, password reset, permissions
docker compose exec backend python manage.py test accounts.tests.test_password_reset
docker compose exec backend python manage.py test accounts.tests.test_permissions
docker compose exec backend python manage.py test accounts.tests.test_schema
docker compose exec backend python manage.py test sales      # sales, credit, voids, isolation
docker compose exec backend python manage.py test purchases  # drafts, receiving, rollback, isolation
docker compose exec backend python manage.py test expenses   # expenses, receipts, net profit, isolation
docker compose exec backend python manage.py check
```

Frontend, inside the running `frontend` container:

```bash
docker compose exec frontend npm test         # Vitest (79 tests): API client, auth pages, app shell, products, stock dialog, sale screen, sales, purchases, expenses, dashboard, languages
docker compose exec frontend npm run lint     # oxlint
docker compose exec frontend npm run build    # type-check + production build (writes frontend/dist)
```

Or locally from `frontend/` after `npm install`: `npm test`, `npm run lint`,
`npm run build`.

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
| GET | `/api/v1/sales/` | Bearer | `sales.view` |
| POST | `/api/v1/sales/` | Bearer | `sales.create` |
| GET | `/api/v1/sales/{id}/` | Bearer | `sales.view` |
| POST | `/api/v1/sales/{id}/payments/` | Bearer | `sales.create` |
| POST | `/api/v1/sales/{id}/void/` | Bearer | `sales.void` (Owner) |
| GET | `/api/v1/sales/summary/` | Bearer | `sales.view` |
| GET/POST/PATCH/DELETE | `/api/v1/customers/` … | Bearer | view / `sales.create` / `sales.void` to delete |
| GET/POST, GET/PUT | `/api/v1/purchases/`, `/api/v1/purchases/{id}/` | Bearer | `purchases.view` / `purchases.manage` |
| POST | `/api/v1/purchases/{id}/receive/`, `…/cancel/` | Bearer | `purchases.manage` |
| GET/POST/PATCH/DELETE | `/api/v1/expenses/` … | Bearer | `expenses.view` / `expenses.manage` / `expenses.delete` (Owner) |
| GET/PUT/DELETE | `/api/v1/expenses/{id}/receipt/` | Bearer | view / `expenses.manage` |
| GET | `/api/v1/expenses/summary/` | Bearer | `expenses.view` |
| GET/POST/PATCH/DELETE | `/api/v1/expense-categories/` … | Bearer | `expenses.view` / `expenses.manage` / `expenses.delete` |

A missing permission returns **403**. Request and response details:
`docs/PHASE_1_SUMMARY.md` §3 (auth), §7 (password reset), §8 (permissions);
catalog and inventory endpoints in `docs/PHASE_2_SUMMARY.md` §5; sales in
`docs/PHASE_3_SUMMARY.md` §4, purchases and expenses in its step 2 section.

```bash
# A cash sale: 2 units, 30,000 handed over (change is computed and stored)
curl -s -X POST localhost:8000/api/v1/sales/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"items":[{"product":"<product id>","quantity":2}],"amount_received":"30000"}' | jq

# On credit: pay 5,000 now, the rest is owed by a new customer
curl -s -X POST localhost:8000/api/v1/sales/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"items":[{"product":"<product id>","quantity":1}],"amount_received":"5000","new_customer":{"name":"Mama Asha","phone":"0712000000"}}' | jq
```

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

Operations are grouped by tag (`auth`, `password reset`, `settings`,
`catalog`, `inventory`, `sales`, `purchases`, `expenses`). Each
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

## 7. Languages (Kiswahili / English)

- **Who sees what.** Kiswahili is the default on a new device. The language
  button next to the theme button switches between Kiswahili and English.
  The choice is saved on that device (`localStorage["bbm.lang"]`), like the
  theme.
- **Wording.** The Swahili is kept simple and casual: everyday shop words,
  short sentences.
- **Frontend.** Text lives in `frontend/src/i18n/en.ts` and `sw.ts` (i18next).
  `sw.ts` must have every key in `en.ts`, or `npm run build` fails. Components
  use `const { t } = useTranslation()` and `t('area.key')`.
- **Server messages.**
  - The frontend sends `Accept-Language: sw` or `en`, and Django answers in
    that language through `LocaleMiddleware`.
  - Our messages use `gettext` (`_()`). Their Kiswahili is in
    `backend/locale/sw/LC_MESSAGES/django.po`, compiled to `django.mo`; both
    files are committed.
  - Django REST framework ships no Kiswahili, so the library messages users
    see are listed in `backend/core/library_messages.py` and translated in the
    same file.
- **Adding or changing a server message:**

  ```bash
  docker compose exec backend python manage.py makemessages -l sw \
    --ignore='venv/*' --ignore='*/tests/*' --ignore='*/migrations/*' --no-obsolete
  # fill in the new msgstr lines in backend/locale/sw/LC_MESSAGES/django.po, then
  docker compose exec backend python manage.py compilemessages -l sw --ignore='venv/*'
  docker compose restart backend
  ```

  `sales.tests.test_i18n` fails if a message is untranslated or the `.mo` is
  out of date.

---

## Repo layout

```
BBM/
├── docker-compose.yml        # db, redis, backend, frontend
├── CLAUDE.md                 # architecture rules + working conventions (for Claude Code)
├── .claude/                  # Claude Code setup: rules/, skills/, agents/, settings.json
├── .env                      # compose vars (gitignored; see .env.example)
├── docs/
│   ├── BBM_SRS_Summary_Draft.pdf
│   ├── PHASE_1_SUMMARY.md
│   ├── PHASE_2_SUMMARY.md
│   └── PHASE_3_SUMMARY.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env                  # Django vars (gitignored; see .env.example)
│   ├── config/               # settings, root urls (API docs routes when DEBUG)
│   ├── locale/sw/            # Kiswahili server messages (django.po / django.mo)
│   ├── core/                 # tenancy: TenantModel, TenantManager, tenant context,
│   │                         #   TenantJWTAuthentication, HasTenantPermission,
│   │                         #   OpenAPI schema hooks (schema.py), middleware, admin base
│   ├── accounts/             # User, Business, Role, UserRole, BusinessSettings,
│   │                         #   Permission, RolePermission, PasswordResetToken;
│   │                         #   rbac.py (permission catalog + role defaults);
│   │                         #   register/login/refresh/logout/me, password reset,
│   │                         #   settings
│   ├── catalog/              # Category, Brand, Supplier, Product, ProductBatch;
│   │                         #   CRUD + product image upload (validators.py)
│   ├── inventory/            # StockMovement ledger, services.py (record_movement,
│   │                         #   derived stock), batches, adjustments, alerts
│   ├── sales/                # Customer, Sale, SaleItem, SaleItemAllocation, Payment;
│   │                         #   services.py (create_sale, record_payment, void_sale,
│   │                         #   derived balances, summary incl. net profit)
│   ├── purchases/            # Purchase, PurchaseItem; services.py (save_draft,
│   │                         #   receive_purchase, cancel_purchase)
│   ├── expenses/             # ExpenseCategory, Expense; receipt validation and
│   │                         #   download, expense totals
│   ├── media/                # product images, dev only (gitignored)
│   └── private_media/        # expense receipts, served only by the API (gitignored)
└── frontend/
    ├── src/i18n/             # i18next setup, en.ts / sw.ts dictionaries
    ├── src/lib/              # api.ts (fetch + token refresh), auth.tsx / auth-context.ts,
    │                         #   schemas.ts (Zod), forms.ts, types.ts, format.ts,
    │                         #   money.ts (cents maths, cart, change), dates.ts
    │                         #   (period ranges), purchases.ts (line maths)
    ├── src/pages/            # auth pages, dashboard, settings, products (list, detail,
    │                         #   form), inventory alerts, catalog setup, sale screen (pos),
    │                         #   sales + receipt, customers, purchases (list, form,
    │                         #   detail), expenses
    ├── src/components/       # layout (app shell, auth layout), shadcn/ui in ui/
    ├── src/routes/guards.tsx # RequireAuth / RedirectIfAuthed
    └── src/test/             # Vitest setup, mockFetch, render helpers, fixtures
```

### Working with Claude Code

`CLAUDE.md` holds the architecture rules and working conventions. `.claude/`
adds:

| Path | What |
|---|---|
| `rules/backend.md`, `rules/frontend.md` | Detailed coding rules, loaded for files under `backend/` / `frontend/` |
| `skills/new-resource/` | Checklist for a new tenant-scoped model, endpoint and page |
| `skills/verify/` | Runs every backend and frontend check and reports the results (`/verify`) |
| `agents/tenancy-reviewer.md` | Read-only review of backend changes against the tenancy, ledger, snapshot and atomicity rules |
| `settings.json` | Pre-approved read-only/test commands; denies reading the `.env` files |
