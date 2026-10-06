---
name: new-resource
description: Checklist for adding a new tenant-scoped model + API endpoint (and optionally its frontend page) in BBM, e.g. expenses, purchases, sales, customers. Use when planning or implementing any new backend resource.
---

# Adding a tenant-scoped resource

CLAUDE.md requires a plan first: present the plan (models, endpoints,
permissions, tests, frontend pages) and wait for approval before writing code.

## 1. Model (`<app>/models.py`)
- [ ] Subclass `core.models.TenantModel`. No `business` field in any form or
      serializer.
- [ ] FKs to other tenant models use `on_delete=PROTECT` and `save()` calls
      `self.check_same_business(...)` after `self.assign_business()`.
- [ ] Per-business uniqueness via `UniqueConstraint("business", ...)`; DB
      `CheckConstraint`s for invariants (non-negative money, signs).
- [ ] Money: `DecimalField(max_digits=12, decimal_places=2)`.
- [ ] Line items (sale/purchase) snapshot price and cost columns.
- [ ] Index `(business, created_at)` if it will be listed/reported by date.
- [ ] Anything touching stock calls `inventory.services.record_movement()`.
- [ ] New app? Add it to `INSTALLED_APPS` and include its urls under
      `/api/v1/` in `config/urls.py` with a namespace.

## 2. Permissions
- [ ] Codenames in `accounts/rbac.py` (`PERMISSIONS`, `DEFAULT_ROLE_PERMISSIONS`;
      Admin never gets `.delete`).
- [ ] Data migration in `accounts/` seeding the codenames and granting them
      to existing Owner/Admin system roles — copy `0004_phase2_permissions.py`,
      literal codenames, explicit `business_id`.
- [ ] Mirror in `frontend/src/lib/types.ts` `PERMISSIONS`.

## 3. API
- [ ] Logic in `<app>/services.py` (with `@transaction.atomic` for multi-row writes).
- [ ] Viewset subclasses `core.views.TenantModelViewSet`; set `model`,
      `serializer_class`, `required_permissions`, `search_fields`,
      `ordering_fields`, `filterset_*`, `protected_message`.
- [ ] Serializer FK fields use `Model.objects.all()` querysets (scoped at
      query time) so other tenants' ids fail validation.
- [ ] `@extend_schema_view` / `@extend_schema` with tags and summaries;
      document 409 where relevant.
- [ ] `makemigrations` for the app.

## 4. Tests (`<app>/tests/`)
- [ ] Model tests: constraints, cross-tenant FK refused.
- [ ] API tests on `catalog.tests.helpers.TenantAPITestCase`: CRUD, filters,
      pagination, 400/409 paths.
- [ ] Permission tests: role without the codename → 403.
- [ ] `test_isolation.py`: business B → 404 on A's detail/update/delete,
      A's ids refused as references, lists empty.
- [ ] Atomic flows: a test that forces a failure mid-way and asserts nothing
      was written (no rows, no stock movement).

## 5. Frontend (if in scope)
- [ ] Types in `lib/types.ts`, Zod schema in `lib/schemas.ts`.
- [ ] Page following `pages/products.tsx` (list) / `pages/product-form.tsx`
      (form); route in `App.tsx`; nav entry in
      `components/layout/sidebar-content.tsx` gated by permission.
- [ ] Vitest tests with `mockFetch` + `renderWithAuth`.

## 6. Docs and handoff
- [ ] Update README (endpoint table, test counts) and the current phase
      summary in `docs/`.
- [ ] Run the `verify` skill, then tell the user what to test manually.
