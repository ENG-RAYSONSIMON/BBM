---
paths:
  - "backend/**"
---

# Backend rules (Django / DRF)

Everything runs in Docker. Run Django commands as
`docker compose exec backend python manage.py <cmd>` (use `run --rm backend`
if the container is down). There is no local Python environment to rely on.

## Tenancy (FR-3, NFR-7)
- Every tenant-owned model subclasses `core.models.TenantModel` (UUID PK,
  timestamps, `business` FK that is `editable=False`).
- Never accept `business` / `business_id` from request data, query params or
  serializer fields. The business comes only from the verified JWT via
  `core.authentication.TenantJWTAuthentication`, or from
  `core.tenancy.tenant_context()` in trusted server code and tests.
- Use `Model.objects` (scoped, fails closed with `TenantContextMissing`).
  `Model.all_objects` is for auth, admin, migrations and system jobs only —
  if you reach for it in a view or service, stop and justify it.
- FKs between tenant models: call `self.check_same_business("fk1", "fk2")` in
  `save()` after `assign_business()` (pattern: `catalog/models.py`).
- `bulk_create()` and `QuerySet.update()` skip `save()`: set `business`
  explicitly and don't use them on `StockMovement`.
- Uniqueness is per business: `UniqueConstraint("business", Lower("name"), ...)`,
  conditional constraints for optional unique fields (SKU, barcode).
- Viewsets for tenant models subclass `core.views.TenantModelViewSet` (scoped
  queryset, `ProtectedError` → 409 with `protected_message`).

## Stock ledger (FR-7, FR-8)
- No stock column anywhere. Stock = sum of `inventory.StockMovement.quantity`.
- All stock changes go through `inventory.services.record_movement()` (atomic,
  locks the batch row, raises `InsufficientStock`). Use `resolve_batch()` to
  pick/create the batch.
- `StockMovement` is append-only: no update, no delete, no API routes for
  either. Sign rules are DB constraints (SALE/DAMAGE/EXPIRY < 0, PURCHASE > 0).
- Read stock via `with_product_stock()` / `with_batch_stock()` annotations —
  don't compute it in Python loops.

## Money path (Phase 3, FR-11–FR-17)
- `sale_items` / `purchase_items` snapshot `unit_price` and `unit_cost` at
  transaction time. Never derive historical profit from current product prices.
- The sale flow (validate stock → sale + items → FEFO batch consumption via
  `record_movement` → COGS/profit from snapshots → payment) is one
  `transaction.atomic()` block; any failure rolls back everything.
- Purchases: `purchases.services.save_draft()` never touches stock.
  `receive_purchase()` locks the purchase and, in one atomic block, resolves
  each line's batch (`resolve_batch`), writes a `PURCHASE` movement via
  `record_movement`, and sets the product's `cost_price` to what was paid.
  Only drafts can be edited or cancelled; a received purchase is corrected
  with stock adjustments.
- Net profit = gross profit (from sale snapshots) −
  `expenses.services.expenses_total()` for the same period (see
  `sales.services` summary).
- Money is `DecimalField(max_digits=12, decimal_places=2)` and `Decimal` in
  Python. Never `float`. Currency is TZS; `TIME_ZONE` is `Africa/Dar_es_Salaam`.

## Files
- Validate uploads in the app's `validators.py` (type + a size limit read
  from `.env`, e.g. `EXPENSE_RECEIPT_MAX_BYTES`). Pattern:
  `catalog/validators.py`, `expenses/validators.py`.
- Private files (expense receipts) use `expenses.models.PrivateStorage`
  under `PRIVATE_MEDIA_ROOT`, in per-business folders. Never put them under
  `MEDIA_ROOT` or `/media/`; serve them only through a permissioned,
  tenant-scoped view (pattern: `expenses.views.ExpenseReceiptView`).

## Permissions (FR-5)
- Every authenticated view declares `required_permissions` — a tuple, or a
  dict of HTTP method → tuple (see `CATALOG_PERMISSIONS` in
  `catalog/views.py`). `()` means "any member". Missing = `ImproperlyConfigured`.
- Access decisions read `RolePermission` rows, never role names.
- New codename: add a constant + description to `accounts/rbac.py`
  (`PERMISSIONS` and `DEFAULT_ROLE_PERMISSIONS`) **and** a data migration in
  `accounts/` that seeds it and grants it to existing system roles, using
  literal codenames (copy the latest,
  `0009_staff_roles_permissions.py`). Mirror it in
  `frontend/src/lib/types.ts` `PERMISSIONS`.
- Buying cost and profit are shown only with `finance.view`: list such
  fields in `finance_fields` on a serializer using
  `core.serializers.FinanceFieldsMixin`. For other in-view decisions use
  `core.permissions.has_permission(request, codename)`.
- A user on a temporary password (`must_change_password`) gets 403 on every
  view except those with `allow_pending_password_change = True`.

## API conventions
- Routes live under `/api/v1/`, namespaced per app (`catalog:product-detail`).
- Every endpoint gets `@extend_schema` / `extend_schema_view` with a `tags`
  and `summary`. `accounts.tests.test_schema` fails on any spectacular warning.
- Lists use the default pagination (`?page=`, `?page_size=` ≤ 100) and
  `django_filters` + `search_fields` + `ordering_fields`.
- Domain errors: 400 for validation, 404 for other tenants' rows (never 403),
  409 for in-use deletes, 403 for missing permission.
- Put business logic in `services.py`, not in serializers or views.

## Messages and languages
- Every message a user can see (validation errors, `protected_message`,
  `Conflict`, `detail`) goes through `gettext` (`_()`). Use `gettext_lazy`
  for module-level and class attributes.
- Use named placeholders, never f-strings:
  `_("%(name)s: only %(count)s available to sell.") % {...}`.
- After adding or changing one, run `makemessages -l sw` and fill in the
  Kiswahili (simple, everyday words), then run `compilemessages`. See README
  §7; `sales.tests.test_i18n` checks it.

## Tests
- Tests use Django's `APITestCase` (not pytest). Shared fixtures live in
  `catalog/tests/helpers.py` (`TenantAPITestCase` with businesses A and B,
  `make_product`, `stock`, `as_user`). Reuse them.
- Every new detail/update/delete endpoint gets a cross-tenant case in the
  app's `test_isolation.py`: business B gets 404 on A's ids, can't reference
  A's rows as FKs, and sees empty lists.
- Every permissioned endpoint gets a test that a role without the codename
  gets 403.

## Secrets
- Never write real secrets. New env vars go in `backend/.env.example` as
  `REPLACE_ME` (or a safe default), read with `env(...)` in
  `config/settings.py`, and documented in README §1.
