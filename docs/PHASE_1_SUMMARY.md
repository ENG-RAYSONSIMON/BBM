# Phase 1 — Identity & Tenant Core

Covers **FR-1** (atomic registration), **FR-2** (JWT with rotating refresh),
**FR-3** (central tenant scoping), **FR-4** (password reset) and **FR-5**
(table-driven permissions) from `docs/BBM_SRS_Summary_Draft.pdf` (v0.2).

Status as of 2026-09-17: implemented. `python manage.py test` runs 53 tests,
all passing. FR-4 and FR-5 are described in §7 and §8; OpenAPI docs in §6.

---

## 1. Apps and layout

| App | Holds |
|---|---|
| `core` | Tenancy plumbing, not tied to a domain: abstract base models, tenant manager, tenant context (ContextVar), JWT authentication class, request middleware, admin base class. It has no concrete models and no migrations. |
| `accounts` | Identity and tenant models (`User`, `Business`, `Role`, `UserRole`, `BusinessSettings`, `Permission`, `RolePermission`, `PasswordResetToken`), registration/RBAC/reset services, permission catalog (`rbac.py`), token helper, auth and settings endpoints. |

`core/views.py` is still the empty `startapp` stub.

---

## 2. Models

### Abstract bases (`backend/core/models.py`)

| Base | Adds |
|---|---|
| `UUIDModel` | `id` UUID primary key (`uuid4`, not editable) |
| `TimeStampedModel` | `created_at` (auto_now_add), `updated_at` (auto_now) |
| `TenantModel` | Both bases above, plus `business` FK → `accounts.Business` (`PROTECT`, `editable=False`); managers `objects` (scoped) and `all_objects` (unscoped); composite index `(business, id)`, named `<class>_biz_id_idx` (NFR-8); `save()` fills in or checks `business` (see §4) |

### `User` (`accounts.User`, `AUTH_USER_MODEL`)

Based on `AbstractUser`, with `UUIDModel` and `TimeStampedModel` added. **It is
not tenant-scoped.** It reaches businesses through `UserRole`, as the SRS
footnote on `users` describes.

Changes from Django's default user:
- `username` is removed; `USERNAME_FIELD = "email"` and `REQUIRED_FIELDS = []`.
- `email` is `unique=True`, and a separate constraint `accounts_user_email_ci_unique`
  on `Lower(email)` makes it unique regardless of case.
- New field `phone` (max 20, may be blank).
- UUID PK plus `created_at`/`updated_at`.
- Custom `UserManager` (`accounts/managers.py`): lowercases email on create,
  and `get_by_natural_key` / `aget_by_natural_key` match with `__iexact`, so
  login ignores case. `create_superuser` requires `is_staff` and `is_superuser`.
- Passwords are hashed with Argon2 (`PASSWORD_HASHERS[0]`), with PBKDF2 kept as
  a fallback (NFR-1). A registration test asserts the stored hash starts with
  `argon2`.

### `Business` (`accounts.Business`) — the tenant

`UUIDModel` + `TimeStampedModel`. It is not a `TenantModel`; it *is* the tenant.

| Field | Notes |
|---|---|
| `name` | required, max 255 |
| `tin` | "TIN", may be blank |
| `phone`, `email`, `address` | may be blank |
| `currency` | max 3, default `"TZS"` |
| `is_active` | default `True`. An inactive business blocks login, refresh and every authenticated request. |

### `Role` (`accounts.Role`) — `TenantModel`

| Field | Notes |
|---|---|
| `name` | max 50; unique per business (`accounts_role_unique_name_per_business`) |
| `is_system` | default `False`; the Owner role created at registration has `True` |

Constants `Role.OWNER = "Owner"`, `Role.ADMIN = "Admin"` (used only for
seeding, never for access decisions — see §8).

### `UserRole` (`accounts.UserRole`) — `TenantModel`

A user's membership of a business.

| Field | Notes |
|---|---|
| `user` | FK → User, `CASCADE`, `related_name="memberships"` |
| `role` | FK → Role, `PROTECT`, `related_name="assignments"` |
| `is_active` | default `True`. Setting it to `False` revokes access on the next request or refresh. |

- Constraint `accounts_userrole_unique_user_per_business`: one membership (so one
  role) per user per business.
- `save()` first runs the tenant check, then raises `TenantMismatch` if
  `role.business_id != business_id`. This stops a membership in business A from
  pointing at a role owned by business B.

### `BusinessSettings` (`accounts.BusinessSettings`) — `TenantModel`

| Field | Default |
|---|---|
| `low_stock_threshold` | `5` (PositiveInteger) |
| `expiry_warning_days` | `30` (PositiveInteger) |
| `tax_rate` | `0` (Decimal 5,2) |
| `loyalty_enabled` | `False` |

Constraint `accounts_businesssettings_one_per_business`: exactly one row per
business. See deviation 3 for how the name differs from the SRS.

### Migrations

- `accounts/migrations/0001_initial.py` creates all five tables, the constraints
  and the `(business, id)` indexes.
- `rest_framework_simplejwt.token_blacklist` migrations (0001–0013) are installed
  for refresh-token blacklisting.

---

## 3. Endpoints

Every route sits under `/api/v1/` (`config/urls.py` → `accounts/urls.py`,
namespace `accounts`). `/admin/` is Django admin.

Defaults (`REST_FRAMEWORK` setting): authentication is
`core.authentication.TenantJWTAuthentication`, and the permission is
`IsAuthenticated`.

| Method | Path | Name | Auth | View → Serializer |
|---|---|---|---|---|
| POST | `/api/v1/auth/register/` | `accounts:register` | none | `RegisterView` → `RegisterSerializer` |
| POST | `/api/v1/auth/login/` | `accounts:login` | none | `LoginView` (SimpleJWT `TokenViewBase`) → `LoginSerializer` |
| POST | `/api/v1/auth/refresh/` | `accounts:refresh` | none | `RefreshView` (SimpleJWT `TokenRefreshView`) → `TenantTokenRefreshSerializer` |
| POST | `/api/v1/auth/logout/` | `accounts:logout` | Bearer access | `LogoutView` → `LogoutSerializer` |
| GET | `/api/v1/auth/me/` | `accounts:me` | Bearer access | `MeView` (plain `APIView`) |

### `POST /auth/register/` — FR-1

Request: `email`, `password`, `business_name` (required); `first_name`,
`last_name`, `phone` (optional).

- The email is lowercased and rejected if it already exists, ignoring case.
  If a concurrent request creates the same email first (race), the resulting
  `IntegrityError` also returns a 400 on `email`.
- The password goes through Django's `AUTH_PASSWORD_VALIDATORS`, which get the
  candidate user so the similarity check works. Failures return 400 on
  `password`.
- It calls `accounts.services.register_owner()`, which is `@transaction.atomic`
  and creates, in order: User → Business → (inside `tenant_context(business)`)
  `seed_default_roles()` (Owner and Admin roles, `is_system=True`, with their
  default `RolePermission` grants) → owner's `UserRole` → `BusinessSettings`.
- **201** body: `{refresh, access, user{id,email,first_name,last_name,phone},
  business{id,name,tin,phone,email,address,currency}, role: "Owner"}`. The new
  owner is logged in immediately.

### `POST /auth/login/` — FR-2

Request: `email`, `password`, optional `business_id`.

- A wrong password and an unknown email return the same **401**
  (`"No active account found with the given credentials."`). A user with no
  active membership gets that same 401 as well.
- If the user has exactly one active membership and no `business_id` was sent,
  that membership is selected.
- If the user has several memberships and no `business_id`, the response is
  **400** with `business_id` error and a `businesses: [{id, name}]` list to
  pick from.
- If `business_id` names a business the user doesn't belong to, the response
  is **400** (`"You are not a member of this business."`). `business_id` only
  chooses among the user's *own* verified memberships.
- **200** body has the same shape as register, with `role` set to the
  membership's role name.

### `POST /auth/refresh/` — FR-2

Request: `refresh`. Before SimpleJWT's normal rotation runs, it checks that the
token's `(user_id, business_id)` still maps to an active membership (active
user, active business). If not, it returns **401** `no_active_membership`.
**200** body: `{access, refresh}`. The old refresh token is blacklisted, so
reusing it returns 401.

### `POST /auth/logout/`

Requires a Bearer access token. Request: `refresh`. The refresh token must be
valid **and belong to the authenticated user**; otherwise the response is 400
`"Token is invalid or expired."`. The token is blacklisted. Returns **204**.

### `GET /auth/me/`

Returns `{user, business, role, permissions}` for the business named in the
token. `permissions` is the sorted list of codenames the role holds (for UI
gating only; the backend enforces them independently).

### Token settings (`SIMPLE_JWT`)

| Setting | Value |
|---|---|
| `ACCESS_TOKEN_LIFETIME` | 20 minutes |
| `REFRESH_TOKEN_LIFETIME` | 7 days |
| `ROTATE_REFRESH_TOKENS` | `True` |
| `BLACKLIST_AFTER_ROTATION` | `True` |

`accounts/tokens.py::tokens_for(user, business)` adds a `business_id` claim
(`core.tenancy.TENANT_CLAIM`) to the refresh token. The access token copies
this claim, and rotation keeps it.

---

## 4. Tenant scoping — mechanism and where it's enforced (FR-3)

### Where the active business comes from

`core/tenancy.py` stores the active business id in a `ContextVar`
(`_current_business_id`, default `None`). It is set in exactly two places:

1. **`core.authentication.TenantJWTAuthentication`**, the DRF default
   authenticator. After SimpleJWT has verified the signature and loaded the
   user, it reads the signed `business_id` claim and calls
   `accounts.services.get_active_membership(user.pk, business_id)`. That
   requires an active `UserRole`, an active user and an active business. If
   there is no match, the request gets **401** `no_active_membership`. If there
   is a match, it sets `request.business`, `request.membership` and the
   ContextVar. **The tenant is never read from the request body, query string
   or headers other than the signed token.**
2. **`core.tenancy.tenant_context(business)`**, a context manager for trusted
   server-side code (registration, tests, and future jobs). It restores the
   previous value on exit and supports nesting.

`core.middleware.TenantContextMiddleware` (in `MIDDLEWARE`, after
`AuthenticationMiddleware`) sets the ContextVar to `None` at the start of each
request and resets it afterwards. This stops a tenant from leaking to the next
request on the same worker. A test asserts the context is `None` after `/me`.

### How queries are scoped

- `TenantModel.objects` is a `TenantManager` (`core/managers.py`). Its
  `get_queryset()` adds `.filter(business_id=CurrentBusinessId())`.
- `CurrentBusinessId` is a custom `Expression`. It reads the ContextVar **when
  the SQL is compiled**, not when the queryset is built (deviation 1). If no
  business is active it raises `TenantContextMissing`, so it **fails closed**.
- `QuerySet.update()` / `.delete()` through `objects` are scoped by the same
  filter. `test_bulk_update_is_scoped` covers `update()`.
- `TenantModel.all_objects` is a plain, **unscoped** `models.Manager`. It is for
  trusted system code only. Current users:
  - `accounts.services.get_active_membership` / `get_active_memberships`: they
    run before any tenant is active, and their result is what picks the tenant.
  - `core.admin.TenantModelAdmin`: admin runs with no tenant. It reads through
    `all_objects`, shows `business` as read-only, and turns off "add".
  - Tests.

### How writes are scoped

`TenantModel.save()` → `assign_business()`:
- If `business_id` is unset and a business is active, it is set to the active
  business.
- If `business_id` is unset and no business is active, it raises
  `TenantContextMissing`.
- If `business_id` is set and differs from the active business, it raises
  `TenantMismatch`.
- `business` has `editable=False`, so ModelForms and ModelSerializers don't
  expose it by default.

`UserRole.save()` also checks that the role belongs to the same business.

### Exceptions

`core.tenancy.TenantContextMissing` and `TenantMismatch` both subclass
`RuntimeError`. Neither is mapped to a DRF response, so if one ever reached a
view it would come back as a 500. That is intentional: it indicates a
programming error, not bad client input.

### Test coverage

| File | Tests | Covers |
|---|---|---|
| `core/tests.py` | 10 | fails closed without context; only the active business's rows are visible; a queryset built early is scoped when it runs; bulk `update()` is scoped; `all_objects` is unscoped; save assigns the business / fails without one / refuses another tenant's business; `UserRole` can't use a role from another business; nested context restores the outer value |
| `accounts/tests/test_registration.py` | 4 | register creates all five rows with an Argon2 hash and returns business-bound tokens; duplicate email rejected regardless of case; weak password rejected with nothing written; a failure on the last step (`BusinessSettings.save`) rolls back User, Business, Role, UserRole and Settings |
| `accounts/tests/test_auth.py` | 10 | same 401 for wrong password and unknown email; single membership selected automatically (with an upper-case email); several memberships require a choice and return the list; non-member `business_id` rejected; refresh rotates and the old token is rejected; refresh rejected after membership deactivated; `/me` reports the token's business and nothing leaks after the request; a token for a business without membership gets 401; access token rejected after deactivation; logout blacklists the refresh token |

---

## 5. Approved deviations from the original plan

### Deviation 1 — Lazy tenant filtering

**Plan:** `TenantManager.get_queryset()` reads the current business id and
filters on that value.

**Built:** the manager filters on `CurrentBusinessId()`, an `Expression` that
reads the ContextVar inside `as_sql()`, i.e. when the query runs.

**Why** (from the docstring in `core/managers.py`): querysets created at import
time, such as a serializer field's `queryset=Role.objects.all()`, would
otherwise capture whichever tenant was active at import (none) or be evaluated
at the wrong moment. With this approach they are scoped to the tenant active
when they run, and still fail closed if there is none.

**Consequence:** building `Role.objects.filter(...)` with no active tenant does
**not** raise. Only running it does. Covered by
`test_queryset_built_early_is_scoped_when_executed`.

### Deviation 2 — Refresh serializer set on the view

**Plan:** set the tenant-aware refresh serializer in
`SIMPLE_JWT["TOKEN_REFRESH_SERIALIZER"]`.

**Built:** `accounts.views.RefreshView(TokenRefreshView)` sets
`serializer_class = TenantTokenRefreshSerializer` directly. `SIMPLE_JWT` has no
`TOKEN_REFRESH_SERIALIZER` entry.

**Consequence:** the membership re-check on refresh applies **only** at
`/api/v1/auth/refresh/`. If SimpleJWT's stock `TokenRefreshView` is ever routed
anywhere else, that route will rotate tokens for deactivated memberships.
Don't add one.

### Deviation 3 — Settings table naming

**SRS §5:** the entity is `settings`.

**Built:** the model is `accounts.BusinessSettings`, so the database table is
`accounts_businesssettings` (verbose name "business settings"). All three tables
from the SRS row `roles / permissions / user_roles` also carry Django's app
prefix: `accounts_role`, `accounts_userrole`, and so on.

### Deviation 4 — Global permission catalog

**SRS §5:** `roles / permissions / user_roles` are all marked tenant-scoped.

**Built:** `accounts.Permission` (the list of codenames) is global, because
codenames are defined in code and mean the same thing in every business.
The tenant-scoped part is `accounts.RolePermission` (which role in which
business holds which permission), a `TenantModel`. Roles and user roles stay
tenant-scoped as before.

**Related difference (Deviation 3):** the SRS lists "currency" under settings. It is actually
stored as `Business.currency`, and `BusinessSettings` has no currency field.

---

## 6. Open TODOs and known gaps

### Against FR-1 (registration)
- [ ] `Role.is_system` help text says system roles "cannot be renamed or
      removed", but **nothing enforces it**: no `save`/`delete` guard and no
      constraint. It only works today because no endpoint edits roles.
- [ ] `Business` has no `logo` field (the SRS lists one under businesses). This
      probably belongs with FR-10/NFR-5 upload validation in Phase 2.
- [ ] `/auth/register/` has no rate limiting (NFR-3).

### Against FR-2 (tokens)
- [ ] No throttling on `/auth/login/` or `/auth/refresh/` (NFR-3). DRF
      `DEFAULT_THROTTLE_*` isn't configured.
- [ ] Outstanding and blacklisted token rows grow without limit. Nothing runs
      SimpleJWT's `flushexpiredtokens` yet; it needs a cron/management-command
      schedule before Phase 4 Celery.
- [ ] The refresh membership check depends on deviation 2 (only that one route).

### Against FR-3 (tenant scoping)
- [ ] Bypasses rely on convention, not enforcement: `all_objects`, raw SQL,
      `bulk_create()` (skips `save()`; documented in the `TenantModel`
      docstring), and `QuerySet.update(business=...)` (which `editable=False`
      doesn't block). Code review is the only guard; there is no lint rule or
      DB-level row security.
- [ ] No cross-tenant **endpoint** tests yet (NFR-7: "guess a valid UUID").
      That's because there are no tenant-owned CRUD endpoints yet. Every
      Phase 2 detail/update/delete endpoint needs one.
- [ ] Every authenticated request costs one extra membership query
      (`select_related` business + role). There is no caching.
- [ ] Future background jobs (Celery, Phase 4) must wrap work in
      `tenant_context()`. The ContextVar doesn't carry into tasks.

### Other Phase 1 items in the SRS that are not built
- [x] **FR-4, password reset** — see §7.
- [x] **FR-5, table-driven permissions** — see §8.
- [ ] No staff/membership management endpoints (inviting an Admin, changing a
      role, deactivating a member). `UserRole.is_active` can only be toggled
      from Django admin.
- [ ] SRS Appendix A says Phase 1 ends when the owner can "land on an empty but
      real dashboard". The frontend isn't started.

### API docs / tooling
- [x] **OpenAPI docs.** Swagger UI `/api/docs/`, ReDoc `/api/redoc/`, schema
      `/api/schema/`, routed only when `DEBUG=True`. `core/schema.py` adds the
      `TenantJWTAuthentication` bearer scheme (`jwtAuth`) and
      `TenantAutoSchema`, which documents each view's `required_permissions`
      (description note + `x-required-permissions`). `manage.py spectacular
      --validate --fail-on-warn` is clean; `accounts/tests/test_schema.py`
      fails on any schema warning or error and checks the DEBUG-only routing.
- [ ] There is no `.env.example` for `./.env` or `./backend/.env`.
- [ ] No CI (NFR-11).
- [ ] `docker-compose.yml` has no `frontend` or `nginx` services, and no db
      healthcheck (`depends_on` is start order only). The backend runs Django's
      `runserver`.
- [ ] Minor: `User.email` has both `unique=True` and the `Lower(email)` unique
      constraint, so two unique indexes. The case-insensitive one is enough.
- [ ] Minor: `UserRole.save()` with no `role` set raises
      `RelatedObjectDoesNotExist` rather than a clean validation error.

---

## 7. FR-4 — Password reset

### Model: `accounts.PasswordResetToken` (not tenant-scoped; users are global)
| Field | Notes |
|---|---|
| `user` | FK → User, CASCADE |
| `token_hash` | SHA-256 hex of the raw token, unique. The raw token is never stored. |
| `expires_at` | creation + `PASSWORD_RESET_TIMEOUT` (default 1800 s) |
| `used_at` | set on use, or when a newer request / completed reset makes it obsolete |

### Endpoints (no authentication, `ScopedRateThrottle` scope `password_reset`, default `5/hour` per IP)
| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/v1/auth/password-reset/` | `email` | always **202** with the same body |
| POST | `/api/v1/auth/password-reset/confirm/` | `token`, `new_password` | **204**; **400** `token` (same text for unknown/used/expired/inactive user); **400** `new_password` for validator failures (token stays usable) |

### Flow (`accounts/services.py`)
- `request_password_reset(email)`: an active user with that email (case-insensitive)
  gets their unused tokens revoked and a new `secrets.token_urlsafe(32)` token.
  The email is sent on commit, with link `{FRONTEND_URL}/reset-password#token=<raw>`
  (fragment keeps it out of server logs and Referer). Unknown or inactive
  email: nothing happens.
- `confirm_password_reset(token, new_password)`: atomic, `select_for_update` on
  the token row; validates the password against the user; sets it; marks every
  unused token for the user as used; blacklists every outstanding refresh
  token for the user (all sessions end).

### Settings
`PASSWORD_RESET_TIMEOUT`, `FRONTEND_URL`, `DEFAULT_FROM_EMAIL`,
`PASSWORD_RESET_THROTTLE_RATE` — all env-overridable, none secret.

### Known gaps
- [ ] Access tokens remain valid for up to 20 minutes after a reset (stateless).
- [ ] Response time differs slightly when the account exists (DB write + mail
      send in the request). Moves off-request with Celery in Phase 4.
- [ ] Throttling uses the default LocMem cache: per-process, reset on restart.
      Point `CACHES` at Redis before running more than one worker.
- [ ] Used/expired token rows are never deleted; add to the same cron as
      `flushexpiredtokens`.
- [ ] Real SMTP not configured. When it is, credentials come from env with
      `REPLACE_ME` placeholders, never literals in settings.

## 8. FR-5 — Table-driven permissions

### Schema
`User → UserRole (per business) → Role → RolePermission → Permission`

| Model | Scope | Notes |
|---|---|---|
| `Permission` | global | `codename` unique (e.g. `settings.manage`), `description`. Read-only in admin. |
| `RolePermission` | `TenantModel` | `role` FK CASCADE, `permission` FK PROTECT; unique `(role, permission)`; `save()` raises `TenantMismatch` if the role belongs to another business |
| `Role.permissions` | — | M2M through `RolePermission` |

### Catalog and defaults (`accounts/rbac.py`)
| Codename | Owner | Admin |
|---|---|---|
| `settings.view` | ✓ | ✓ |
| `settings.manage` | ✓ | |

Migration `0003_seed_permissions` inserts the catalog and backfills existing
businesses (creates their Admin role, grants defaults). It uses literal
codenames so later catalog edits don't change it.

**Adding a permission:** add it to `PERMISSIONS` and `DEFAULT_ROLE_PERMISSIONS`,
then write a data migration inserting the catalog row and granting it to
existing businesses' roles. `seed_default_roles()` raises if a default
codename is missing from the catalog table.

**Adding a role (e.g. Cashier):** create the `Role` and its `RolePermission`
rows. No code changes; covered by `test_new_role_needs_no_code_change`.

### Enforcement (`core/permissions.py::HasTenantPermission`)
- In `DEFAULT_PERMISSION_CLASSES` after `IsAuthenticated`.
- Views declare `required_permissions`: a tuple (all methods) or a dict of
  HTTP method → tuple. HEAD uses GET's entry.
- Fails closed: undeclared view → `ImproperlyConfigured` (500, programming
  error); method not in the dict → 403; no `request.membership` → 403.
- Grants come from `get_permission_codenames(membership)`, which reads
  `RolePermission` through the tenant-scoped manager and caches on the
  membership for the request (one extra query on protected requests).
  Permissions are not in the JWT, so role changes apply on the next request.
- Views with their own `permission_classes` (register, login, refresh,
  password reset) are unaffected. `MeView` and `LogoutView` declare `()`.

### Endpoint: `/api/v1/settings/` (`accounts:settings`)
| Method | Needs | Notes |
|---|---|---|
| GET | `settings.view` | the active business's `BusinessSettings` row |
| PATCH | `settings.manage` | `low_stock_threshold`, `expiry_warning_days`, `tax_rate` (0–100), `loyalty_enabled`; unknown fields (e.g. `business`) are ignored |

No id in the URL: the row is found via the tenant-scoped manager.

### Known gaps
- [ ] No API to manage roles or grants yet (Django admin only). When one is
      built it needs a no-escalation rule: a caller may only assign roles or
      grants that are a subset of their own permissions.
- [ ] `Role.is_system` is still not enforced (see §6); deleting a system role's
      grants in admin takes effect immediately.
- [ ] Only settings permissions exist. Each later phase adds its codenames
      (products, sales, audit log, …) with a data migration.
