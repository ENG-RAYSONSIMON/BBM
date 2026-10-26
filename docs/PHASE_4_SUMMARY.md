# Phase 4 — Reporting, Notifications & Audit (step 1: audit log, step 2: reports)

Covers **FR-20** (sensitive actions logged, readable only by the Owner) from
`docs/BBM_SRS_Summary_Draft.pdf`. Reports with CSV export (FR-18) are step 2
and the notification centre (FR-19) is step 3.

Status as of 2026-10-26: step 1 committed (`a0ac5a8`); step 2 is at the end of this file.
- Backend: 219 tests (203 before, 16 new). The schema validates with `--fail-on-warn`.
- Frontend: 83 Vitest tests (4 new).

Decisions taken with the product owner:
- **Order:** audit log → reports + CSV → notifications. Audit comes first so CSV exports are logged from day one.
- **No Celery yet.** Step 3 notifications are made by a cron-run management command.
- **Logged actions:** deletes, settings changes, role changes, sale voids, purchase cancellations, expense edits (including receipt replace/remove), exports. Logins are not logged.

---

## 1. App: `audit`

| Model | Holds |
|---|---|
| `AuditLog` | `actor` (User, nullable for system actions), `action`, `target_type` (model name), `target_id`, `target_label` (the target's name at the time, so it still reads after a delete), `changes` (JSON: `{field: [old, new]}` or details such as `reason`), `ip_address`. Indexes `(business, created_at)`, `(business, action)`. **Append-only**: `save()` refuses updates and a `pre_delete` guard refuses deletes, as with `StockMovement`. |

**`audit.services`**
- `record(action, *, target, label, changes, actor, ip, business)` writes one entry. Actor and IP default to the request's; the business comes from the tenant context (or `business=` in Django admin, which has none). Call it **inside the action's transaction**, so a refused or rolled-back action leaves no entry. Record deletes *before* deleting (the target loses its pk afterwards).
- `diff(instance, data)` returns `{field: [old, new]}` for fields that actually change. Call it before saving.

**`core.actor`**: a request-scoped `Actor(user, ip)` ContextVar, set by `TenantJWTAuthentication` next to the business and cleared per request by `TenantContextMiddleware`. `client_ip()` uses DRF's throttle identity (honours `NUM_PROXIES`) and keeps only a single valid address.

## 2. Where entries are written

| Action | Hook |
|---|---|
| `DELETE` | `core.views.TenantModelViewSet.perform_destroy` (categories, brands, suppliers, expenses, expense categories, customers), `catalog.views.ProductViewSet.perform_destroy`. A 409 delete is not logged. |
| `SETTINGS_CHANGE` | `accounts.views.BusinessSettingsView.perform_update` (only when something changed). |
| `EXPENSE_CHANGE` | `ExpenseViewSet.perform_update` (changed fields only), receipt PUT/DELETE in `ExpenseReceiptView`. |
| `SALE_VOID` | `sales.services.void_sale` (reason, amount refunded). |
| `PURCHASE_CANCEL` | `purchases.services.cancel_purchase` (reason). |
| `ROLE_CHANGE` | Django admin edits/deletes of `Role`, `RolePermission`, `UserRole` (`accounts.admin.RoleChangeAuditMixin`). There is no staff/roles API yet; when one is built it calls `record()` the same way. |
| `EXPORT` | Reserved for step 2 CSV downloads. |

## 3. Permission and API

- New codename **`audit.view`**, Owner only (`accounts/rbac.py`, migration `accounts/0007_phase4_audit_permission`). Admin gets 403.
- `GET /api/v1/audit-logs/` and `/api/v1/audit-logs/{id}/`: read-only (other methods 405), newest first, paginated. Filters: `action`, `actor` (user id), `target_type`, `date_from`, `date_to`; `search` on the target label. Another business's entry is 404.
- Django admin shows entries read-only.

## 4. Frontend

- `/audit` page (`pages/audit.tsx`): filter by action and dates, search, table on desktop and cards on mobile. Action names, target types and field names are translated (`audit.*` keys in `en.ts` / `sw.ts`); unknown field names fall back to the raw key.
- Sidebar link "Audit log" / "Kumbukumbu", shown only with `audit.view`.

## 5. Known gaps

- [ ] No purge or retention policy; the table only grows. Fine at current volumes.
- [ ] `QuerySet.update()` and `bulk_update()` on `AuditLog` are refused in Python, but raw SQL could still change rows. A DB trigger would close that before going live.
- [ ] Creates (new products, sales, etc.) aren't logged; the SRS asks only for sensitive actions.
- [ ] Product edits (e.g. a price change) and stock adjustments aren't audit-logged; adjustments are already in the stock ledger with who and why.
- [ ] Deleting a user who has audit entries is refused (`actor` is PROTECT), so who-did-what is never lost.

---

# Step 2: reports with CSV export (FR-18)

Status as of 2026-10-26: implemented, not yet committed.
- Backend: 238 tests (219 after step 1, 19 new). The schema validates with `--fail-on-warn`.
- Frontend: 88 Vitest tests (5 new).

Decisions:
- **Reports:** sales, profit, expenses (by day, week, month or year), stock value, and expiry.
- **Default range:** the last 30 days, by day. A daily report is limited to 366 days; pick week, month or year for longer ranges. Dates must fall between 2000 and a year from today, and a range can be at most 10 years (400 otherwise, never a 500).
- **Weeks start on Monday.** A period's row is labelled with its first day, even when the range starts mid-period (the figures still only count dates inside the range).
- **Owner and Admin** get `reports.view` and `reports.export` by default. Like every permission, a business can change that per role. Downloading needs both: export alone is refused.
- **Every CSV download is audit-logged** (`EXPORT`, with the report, its parameters and row count).

## S2.1 App: `reports` (no models)

**`reports/services.py`**, read-only, all through the tenant-scoped managers:

| Report | Rows | Source |
|---|---|---|
| `sales_report` | per period: sales, revenue, discounts, cost of goods, gross profit, cash collected | completed sales' snapshots (`total`, `cost_total`; voids left out), payment ledger (payments − refunds) |
| `profit_report` | per period: revenue, cost of goods, gross profit, expenses, net profit | sale snapshots, expenses by `expense_date` |
| `expenses_report` | per period × category with spending | expenses |
| `stock_valuation_report` | per product holding stock (archived too): stock, cost and selling price, value at each | stock ledger × the product's **current** prices (batch cost isn't stored) |
| `expiry_report` | batches with stock (archived products too, marked), expired or expiring within N days (default 60), soonest first | stock ledger, value at current cost |

Periods are cut with `Trunc(..., output_field=DateField())` in the shop's time zone (Africa/Dar_es_Salaam), and empty periods are filled with zeros so charts have no gaps.

## S2.2 API

| Method | Path | Permission |
|---|---|---|
| GET | `/api/v1/reports/{sales,profit,expenses}/?period=&date_from=&date_to=` | `reports.view` |
| GET | `/api/v1/reports/stock-valuation/` | `reports.view` |
| GET | `/api/v1/reports/expiry/?within_days=` (1–365) | `reports.view` |
| GET | `/api/v1/reports/<report>/export/` with the same parameters | `reports.export` |

JSON answers carry `rows` and `totals` (plus `period`/`date_from`/`date_to`, or `as_of`). CSV is UTF-8 with a BOM so Excel shows Kiswahili correctly; column headers follow `Accept-Language`. Text that starts like a formula (`=`, `+`, `-`, `@`) is written with a leading `'` so Excel shows it as text; numbers, including negative profit, stay numbers. Bad parameters are 400 and nothing is logged.

## S2.3 Frontend

- `/reports` page (`pages/reports.tsx`): report buttons, "show by" day/week/month/year, date range, expiry window (30/60/90 days). Each report has total tiles, a bar chart (sales value, net profit or expenses per period) and a full table (cards on mobile). The table is the text view of the chart.
- "Download CSV" appears only with `reports.export`.
- Charts use Recharts (now a dependency), one hue (`--report-series` in `index.css`), validated for contrast on light and dark cards. The page is a lazy chunk; Recharts adds about 106 kB gzipped there, not to the main bundle.
- Sidebar link "Reports" / "Ripoti" with `reports.view`.

## S2.4 Known gaps

- [ ] Stock value and expiry value use each product's latest cost price (said in the API's field help and on the page), not what each batch cost. Received batches' real costs are on their `PurchaseItem`; valuing each batch at that, falling back to the cost price for opening stock and adjustments, is a follow-up.
- [ ] No outstanding-credit column per period; the dashboard shows what customers owe overall.
- [ ] The reports permission shows profit and expense figures even to a role without `expenses.view` (the dashboard hides them in that case).
- [ ] Reports aren't cached; each request queries live data. Fine at single-shop volumes.
