# Phase 4 — Reporting, Notifications & Audit

Covers **FR-20** (sensitive actions logged, readable only by the Owner) from
`docs/BBM_SRS_Summary_Draft.pdf`. Reports with CSV export (FR-18) are step 2
and the notification centre (FR-19) is step 3.

Status as of 2026-10-27: step 1 committed (`a0ac5a8`); steps 2–4 and the gap fixes follow below.
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
| `ROLE_CHANGE` | Django admin edits/deletes of `Role`, `RolePermission`, `UserRole` (`accounts.admin.RoleChangeAuditMixin`). Staff changes made in the app are logged as `STAFF_ADD`, `STAFF_CHANGE` and `STAFF_PASSWORD_RESET` (step 4). |
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
- [x] ~~Raw SQL could still change rows.~~ Closed: a Postgres trigger (`audit/0003_immutable_trigger`) refuses every UPDATE and DELETE on `audit_auditlog`.
- [ ] Creates (new products, sales, etc.) aren't logged; the SRS asks only for sensitive actions.
- [ ] Product edits (e.g. a price change) and stock adjustments aren't audit-logged; adjustments are already in the stock ledger with who and why.
- [ ] Deleting a user who has audit entries is refused (`actor` is PROTECT), so who-did-what is never lost.

---

# Step 2: reports with CSV export (FR-18)

Status as of 2026-10-26: committed (`9997253`).
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

- [x] ~~Stock value used each product's latest cost price.~~ Closed: each batch is valued at the average paid on its received purchases (`reports.services.with_batch_cost`), falling back to the product's cost price for opening stock and adjustments.
- [ ] No outstanding-credit column per period; the dashboard shows what customers owe overall.
- [x] ~~Reports showed spending without `expenses.view`.~~ Closed: the expenses and profit reports need `expenses.view` (403 otherwise, JSON and CSV), and the page hides them.
- [ ] Reports aren't cached; each request queries live data. Fine at single-shop volumes.

---

# Step 3: notification centre (FR-19)

Status as of 2026-10-26: committed (`65c1d69`).
- Backend: 255 tests (238 after step 2, 17 new). The schema validates with `--fail-on-warn`.
- Frontend: 94 Vitest tests (6 new).

Decisions:
- **No Celery.** `manage.py generate_notifications` makes the alerts; production runs it hourly in a `scheduler` service (see `docs/DEPLOYMENT.md`, "Scheduled jobs"). In development, run it by hand.
- **One alert per problem, not per run.** A notification stays *open* while its condition lasts, with its figures (stock, days left) refreshed each run, and is *resolved* when it ends (restocked, batch sold or written off). If the problem comes back, a new one opens.
- **Read state is per person**, since one business-wide alert reaches everyone who can see stock.
- **Outside channels are reserved:** email, SMS and WhatsApp exist as interfaces but have no provider (FR-23, Phase 5). Using one logs an error and raises, never pretends to succeed.

## S3.1 App: `notifications`

| Model | Holds |
|---|---|
| `Notification` | `kind` (`LOW_STOCK`, `EXPIRING`, `EXPIRED`), `channel` (`IN_APP`; `EMAIL`/`SMS`/`WHATSAPP` reserved), `recipient` (empty = business-wide), `required_permission` (stock alerts: `inventory.view`), `params` (product, name, stock, batch, expiry date, days), target product, `dedupe_key`, `resolved_at`. A partial unique constraint allows one **open** notification per key per business. No text is stored: the client writes it from `kind` + `params` in the reader's language. |
| `NotificationRead` | Who read which notification. |

**`notifications/services.py`**
- `sync_stock_notifications(today)`, atomic for the active business: opens alerts for active products at or under their reorder level (or the business threshold), batches expiring within the business's expiry warning days, and expired batches still holding stock. It refreshes the figures of open ones and resolves those whose condition ended. Concurrent runs can't open duplicates (the constraint plus `ignore_conflicts`).
- `visible_to(user, codenames)`: the caller's business-wide and personal notifications whose required permission they hold, with `is_read`.
- `mark_read`, `mark_all_read` (only what the caller can see).

**`notifications/channels.py`**: `deliver(notification, user)`. In-app does nothing (the row is the delivery); the reserved channels raise `ChannelNotConfigured`.

**`generate_notifications`** walks every active business in its own tenant context. One failing business is reported and the rest still run; the command then exits with an error.

## S3.2 API (any member; each notification needs its own permission)

| Method | Path | Does |
|---|---|---|
| GET | `/api/v1/notifications/` (`?unread=true`, `?open=true`, `?kind=`) | My notifications, newest first |
| GET | `/api/v1/notifications/{id}/` | One notification (404 if not mine to see) |
| POST | `/api/v1/notifications/{id}/read/` | Mark read (204) |
| POST | `/api/v1/notifications/read-all/` | Mark all read (204) |
| GET | `/api/v1/notifications/unread-count/` | `{"unread": n}`: open and unread |

## S3.3 Frontend

- A bell with the unread count in the sidebar footer and the mobile top bar. It checks every minute and links to `/notifications`.
- `/notifications`: alerts in plain words ("Shea Butter is running low: 3 pcs left."), New/Sorted badges, "All" / "New only", "Mark all read". Tapping an alert marks it read and opens its product.

## S3.4 Known gaps

- [ ] Alerts appear up to an hour after stock changes (the scheduler interval), not instantly.
- [ ] No notifications other than stock ones yet (e.g. a customer's credit overdue).
- [x] ~~The scheduler has no healthcheck.~~ Closed: clean runs touch a heartbeat file; the service is unhealthy after two hours without one.
- [x] ~~Old resolved notifications are never cleaned up.~~ Closed: `manage.py cleanup` deletes those resolved more than `NOTIFICATION_RETENTION_DAYS` (90) ago.

---

# Step 4: staff accounts (Sellers and Cashiers)

Status as of 2026-10-26: committed (`eca152b`).
- Backend: 282 tests (255 after step 3, 27 new). The schema validates with `--fail-on-warn`.
- Frontend: 110 Vitest tests (16 new, including the show-password eye).

Decisions taken with the product owner:
- **Email + temporary password.** The Owner (or an Admin) sets it when adding someone; they must choose their own at first login.
- **Fixed roles for now:** Seller and Cashier join Owner and Admin as system roles. There is no screen to edit what a role may do yet.
- **Cost and profit hidden** from anyone without `finance.view`, enforced by the server.
- **The Cashier runs the money path** for an owner who may be far away: sales and repayments, products and stock, purchases and expenses, with buying prices and profit. Never deletes or voids; no reports, settings, staff or audit log. Migration `accounts/0011_cashier_runs_the_shop` gives existing Cashier roles the extra grants.
- **Only new emails.** The plan let an email that already had an account (e.g. from another shop) join with its own password. The tenancy review found that this lets a shop take over that account here: a shop that created an account knows, or has reset, its password. With no email verification, nothing proves an existing account belongs to the person being added, so the staff API refuses existing emails. A person who works at two shops needs two emails for now (or Django admin).

## S4.1 Roles and permissions

New codenames (`accounts/rbac.py`, migration `accounts/0009_staff_roles_permissions`, which also creates Seller and Cashier in every existing business):

| Codename | Means | Owner | Admin | Cashier | Seller |
|---|---|---|---|---|---|
| `sales.view_all` | everyone's sales and the sales totals | ✓ | ✓ | ✓ | – |
| `payments.create` | credit repayments (split out of `sales.create`) | ✓ | ✓ | ✓ | – |
| `finance.view` | buying cost and profit | ✓ | ✓ | ✓ | – |
| `staff.manage` | add and manage staff | ✓ | ✓ | – | – |

Seller: `catalog.view`, `inventory.view`, `sales.view`, `sales.create`. Cashier: the same plus `sales.view_all`, `payments.create`, `finance.view`, `catalog.manage`, `inventory.adjust`, `purchases.view`/`manage` and `expenses.view`/`manage`. It holds no `.delete`, `sales.void`, `reports.*`, `settings.*`, `staff.manage` or `audit.view`, so it stays below Admin and an Admin can still add Cashiers.

- Without `sales.view_all` the sale list, detail, payment and void views only see the caller's own sales (others are 404), and `/sales/summary/` is 403.
- Without `finance.view`, `core.serializers.FinanceFieldsMixin` leaves out product `cost_price`, sale `cost_total` / `gross_profit` and item `unit_cost` / `line_cost`. The summary returns `cogs`, `gross_profit` and `net_profit` as null.
- **Who may give which role:** only a role with *fewer* powers than your own (its permissions a strict subset of yours). So an Admin can add Sellers and Cashiers but not Admins, and nobody can give Owner or change the Owner (Owner holds every permission). Nobody can change themselves. This reads permission rows, not role names.

## S4.2 Accounts and the API

- `User.must_change_password` (migration `0010`). While it is set, `HasTenantPermission` answers 403 (`password_change_required`) on every view except me, logout and change-password. A reset by email also clears it.
- Login now records `last_login` (shown on the staff list).

| Method | Path | Does |
|---|---|---|
| GET/POST | `/api/v1/staff/` | List; add someone: creates an account with the temporary password. An email that already has an account is refused (400). |
| GET/PATCH | `/api/v1/staff/{id}/` | Change role or `is_active`. Turning off works from their next request; their sales stay. No delete. |
| POST | `/api/v1/staff/{id}/reset-password/` | New temporary password, logs them out everywhere. Refused if the account also belongs to another business (possible only via Django admin), and for platform operators (`is_staff`/`is_superuser`). |
| GET | `/api/v1/roles/` | Roles, with `assignable` for the caller. |
| POST | `/api/v1/auth/change-password/` | Current + new password; ends other sessions, returns fresh tokens. |

Ids are membership (`UserRole`) ids, so another business's staff are 404. Each add, change and reset writes an audit entry in the same transaction.

## S4.3 Frontend

- `/staff` (sidebar "Staff" / "Wafanyakazi", with `staff.manage`): list with role, status, temporary-password badge and last login; Add dialog with "Make one for me" and "Copy login details" (text ready for WhatsApp/SMS); a dialog to change role, turn access off/on or give a new password.
- `/change-password`: forced after login on a temporary password (route guard), and reachable any time from "My password" in the sidebar footer.
- Role names are translated (Mmiliki, Msimamizi, Muuzaji, Keshia).
- Dashboard: sales tiles need `sales.view_all`, profit tiles `finance.view`. Sales list is titled "My sales" without `sales.view_all`. Cost and profit rows show only when the server sends them.

## S4.4 Known gaps

- [ ] No screen to edit what each role may do (the tables allow it; Django admin only).
- [ ] One account can't work at two shops through the app; that needs an email invite the person accepts.
- [x] ~~Name and phone can't be edited.~~ Closed: `PATCH /api/v1/staff/{id}/` takes `first_name`, `last_name`, `phone` (audit-logged), refused for an account also used at another business.
- [x] ~~No "my sales today" tile.~~ Closed: `GET /api/v1/sales/my-summary/` (`sales.view`) gives the caller's own sales and cash today, no cost or profit; sellers see it on the dashboard.
- [x] ~~Reports showed profit regardless of `finance.view`.~~ Closed: the profit, stock-value and expiry reports need `finance.view` too (403 otherwise, JSON and CSV), and the sales report leaves out `cogs` and `gross_profit` without it.

---

# Gap fixes and production URLs (2026-10-27)

Status: implemented, not yet committed.
- Backend: 296 tests (282 before, 14 new). Frontend: 113 Vitest tests (3 new). The schema validates with `--fail-on-warn`.
- Closed the gaps marked [x] above: the audit trigger, staff name/phone edits, the seller's tile, `finance.view` on reports, and stock valued at batch cost.
- Pre-production hardening: DB triggers make stock movements and payments append-only at the database too; `manage.py cleanup` runs daily from the scheduler; the scheduler has a heartbeat healthcheck; the expenses and profit reports need `expenses.view`; a same-phone customer race is a 400.
- Links people are sent use the live address even in development: `FRONTEND_URL` (password-reset links) and the new `VITE_APP_URL` (staff login details), both `https://bbm.mauzo.tz`. Set in `.env.example`, `docker-compose.yml`, the frontend `Dockerfile` and the image workflow.
