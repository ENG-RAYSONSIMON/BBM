# Phase 3 — The Money Path (step 1: cash sales and credit)

Covers **FR-11** (atomic sale), **FR-12** (full rollback), **FR-13** (overselling
blocked), **FR-16** (gross profit from snapshotted cost) and **FR-17** (live
dashboard figures) from `docs/BBM_SRS_Summary_Draft.pdf` (v0.2), for cash
sales. Purchases (FR-14), expenses (FR-15) and net profit are the next steps.

Status as of 2026-10-10: implemented and committed (`6beee83`). Step 2 (purchases,
expenses, net profit) is described at the end of this file.
- Backend: 154 tests (120 from Phases 1–2, 34 new). The schema validates with `--fail-on-warn`.
- Frontend: 47 Vitest tests (16 new).

Decisions taken with the product owner:
- **Cash only.** The seller enters the cash received; the system stores the change given.
- **Credit (lending) is allowed.** A customer may pay part or nothing, and pays off the rest later.
- **Overselling is always blocked.** The FR-13 override is deferred.
- **Extras in this step:** per-line discount, voiding a sale, and customer name and phone.

---

## 1. App: `sales`

| Model | Holds |
|---|---|
| `Customer` | `name`, `phone` (unique per business when not blank), `notes`. Required for a sale on credit. |
| `Sale` | `number` (receipt `S-000001`, sequential per business), `status` (`COMPLETED`/`VOID`), `customer`, `sold_by`, `subtotal`, `discount_total`, `total`, `cost_total`, `note`, void fields. DB checks: amounts ≥ 0, `total = subtotal − discount_total`. Index `(business, created_at)`. |
| `SaleItem` | `product`, `quantity` > 0, plus snapshots: `unit_price` and `unit_cost` copied from the product, `discount` (TZS for the whole line, ≤ qty × price), `line_total`, `line_cost`. DB checks hold the arithmetic. |
| `SaleItemAllocation` | Which batch each line's units came from (FEFO), so a void returns stock exactly. |
| `Payment` | `kind` (`PAYMENT`/`REFUND`), `method` (`CASH`; it's a choices field, ready for M-Pesa), `amount` > 0, `amount_received`, `change_given`, `received_by`, `note`. **Append-only**, guarded like `StockMovement`. Index `(business, created_at)`. |

All of these are `TenantModel`s, and every FK calls `check_same_business()`.

**Derived, not stored:**
- **`amount_paid`, `balance` and `payment_status`** (`PAID`/`PARTIAL`/`UNPAID`/`VOID`) are computed from the sale's payments (payments − refunds) by `with_payment_totals()`.
- **A customer's `balance`** is computed the same way over their completed sales (`with_customer_balance()`).

**Inventory change:** a new `StockMovement` type `RETURN` (must be positive, enforced by a DB check). Voids write it.

## 2. Services (`sales/services.py`)

### `create_sale()`: one `transaction.atomic()` block
1. Validate the lines:
   - active product
   - quantity ≥ 1
   - discount between 0 and the line amount
   - each product listed once.
2. If the cash received is less than the total, require a customer (existing, or `new_customer`).
3. Lock the business's `BusinessSettings` row, which serialises receipt numbers.
4. Lock every batch of the products being sold, ordered by id so concurrent sales can't deadlock.
5. Check sellable stock. Batches are taken FEFO: earliest expiry first, batches without expiry last, then oldest `received_on`. **Expired batches are never sold.** A shortage is a 400 naming the product, and nothing is written.
6. Create the customer if new, then the sale and its items (price and cost snapshotted from the product, never from the client).
7. Write one `SALE` movement and one allocation per batch, through `record_movement()`.
8. Write the payment: `paid = min(received, total)`, `change = received − paid`. No payment row when nothing is paid.

### Other services
- **`record_payment()`** (credit repayment):
  - locks the sale
  - refuses a sale that is void or has nothing owed
  - applies `min(received, balance)` and stores the change.
- **`void_sale()`**:
  - needs a reason
  - writes a `RETURN` movement per allocation, back into the original batches
  - writes a `REFUND` for the net cash collected
  - marks the sale `VOID`. Nothing is deleted.
- **`sales_summary(date_from, date_to)`**:
  - over completed sales in the range: `sales_count`, `revenue`, `discounts`, `cogs`, `gross_profit`
  - `cash_collected`: payments − refunds made in the range
  - `outstanding_credit`: everything still owed, all time.
  - Profit counts on the sale date even when the sale is on credit.

## 3. Permissions

New codenames in `accounts/rbac.py`, plus data migration `accounts/0005_phase3_sales_permissions.py`:

| Codename | Owner | Admin |
|---|---|---|
| `sales.view` (sales, customers, summary) | ✓ | ✓ |
| `sales.create` (sell, record payments, add/edit customers) | ✓ | ✓ |
| `sales.void` (void a sale, delete a customer) | ✓ | |

## 4. Endpoints (under `/api/v1/`)

| Endpoint | Permission | Notes |
|---|---|---|
| `GET sales/` | `sales.view` | Filters: `date_from`, `date_to`, `status`, `payment_status`, `customer`, `sold_by`, `receipt` (`S-000012` or `12`). Search: customer name/phone, note. Ordering: `created_at`, `number`, `total`, `balance`. |
| `POST sales/` | `sales.create` | `{items: [{product, quantity, discount?}], amount_received, customer? \| new_customer?: {name, phone?}, note?}`. Returns 201 with the full sale. |
| `GET sales/{id}/` | `sales.view` | Items (with batch allocations), payments, derived totals, void info. There is no PUT, PATCH or DELETE. |
| `POST sales/{id}/payments/` | `sales.create` | `{amount_received, note?}` → 201 with the payment. |
| `POST sales/{id}/void/` | `sales.void` | `{reason}` → 200 with the sale. |
| `GET sales/summary/` | `sales.view` | `?date_from&date_to`. The default is today in Africa/Dar_es_Salaam. |
| `GET/POST customers/`, `GET/PATCH/DELETE customers/{id}/` | view / create / void | `balance`, `total_bought` and `amount_paid` are annotated. Filter `has_balance=true\|false` (debtors). Deleting a customer who has sales is a 409. |

Errors not tied to a field (e.g. "This sale is already void.") come back as `non_field_errors`.

## 5. Frontend

- **Pages:**
  - **`/pos` (New sale):**
    - product search, with out-of-stock products disabled
    - cart with quantity steppers and per-line discount
    - live subtotal, discount and total
    - "Cash received" shows the change or the amount going on credit, with "Exact cash" and "All on credit" shortcuts
    - customer picker (search, or add a new one inline), required when something is owed
    - saving goes to the receipt.
  - **`/sales`:** search (receipt number, customer), payment-status and date filters, and `?customer=` from the customers page.
  - **`/sales/:id`:** receipt with items (and the batches they came from), totals, cost and gross profit, payment history, **Record payment** (shows the change) and **Void** (needs a reason; `sales.void` only).
  - **`/customers`:** balances, an "Owes money" filter sorted by largest debt, and an add-customer dialog. A row opens that customer's sales.
- **Dashboard:** live tiles for Today's sales (and count), Today's profit, Cash collected today, and Owed by customers. Expenses stays a placeholder.
- **Navigation:** New sale, Sales and Customers, gated by permission.
- **Routes:** pages other than the dashboard and product form are lazy-loaded.
- **Shared code:** `lib/money.ts` holds the cart and cash maths, in integer cents.

## 6. Tests

### Backend (`sales/tests/`)
- **`test_sales.py`:**
  - totals, change and receipt numbering per business
  - snapshots survive later price changes; the client can't send price or cost
  - FEFO across batches, and expired batches are skipped
  - insufficient stock writes nothing
  - line validation
  - forced mid-transaction failure rolls back every row and movement
  - credit with new and existing customers; duplicate phone
  - filters; permissions (403s); sales are immutable; customer CRUD and the 409.
- **`test_payments_void.py`:**
  - repayments and change; refusals
  - payments are append-only
  - a void returns stock to the original batches and refunds cash; double void; Admin can't void
  - the NFR-9 reconciliation still holds
  - summary maths and date validation.
- **`test_isolation.py` (NFR-7):**
  - 404 on another business's sale, customer, payment and void routes
  - its lists and summary come back empty
  - its product and customer ids are refused.

### Frontend
- money maths
- the sale screen: totals, change, request body, credit needing a customer, server stock error, out-of-stock products
- sales list states
- receipt: repayment, void gating and reason, server error
- nav gating; dashboard tiles.

## 7. Known gaps
- [ ] The overselling override (FR-13) is not built; selling more than you have is always refused.
- [ ] Only cash. M-Pesa, Tigo Pesa, Airtel Money and card need new `Payment.Method` values plus a reference field.
- [ ] No partial returns: a void cancels the whole sale.
- [ ] No printable or WhatsApp receipt yet (FR-22 print formatting is Phase 5).
- [ ] Customers can be added but not edited from the UI. The API supports PATCH.
- [ ] Net profit (FR-16 second half) needs expenses (FR-15).
- [ ] `stock_on_hand` on the sale screen includes expired stock; the server refuses it at save time with a clear message.
- [ ] The main JS chunk is still about 627 kB. Route splitting moved the pages out, but shared libraries dominate; vendor chunking is a separate task.
- [ ] `QuerySet.update()` / `bulk_create()` on `Payment` bypass the append-only guard, the same as `StockMovement`.
- [ ] Two simultaneous requests creating a customer with the same phone: the second gets a 500 (unique constraint) instead of a 400. Data stays consistent.

---

# Step 2: purchases, expenses and net profit

Covers **FR-14** (a received purchase adds stock and writes `PURCHASE`
movements in one transaction), **FR-15** (categorised expenses with an optional
validated receipt), the second half of **FR-16** (net profit = gross profit −
period expenses) and the date range of **FR-17**.

Status as of 2026-10-13: implemented, not yet committed.
- Backend: 195 tests (154 from step 1 and earlier, 41 new). The schema validates with `--fail-on-warn`.
- Frontend: 70 Vitest tests (23 new).

Decisions taken with the product owner:
- **Draft → Receive.** A draft can be edited and holds no stock. Receiving is final; only a draft can be cancelled. Stock mistakes after receiving are fixed with adjustments.
- **No supplier payments or credit yet.** A purchase records only what it cost.
- **Latest cost wins.** Receiving sets each product's `cost_price` to the unit cost just paid. Future sales snapshot it; past sales keep their own snapshots.
- **Receipts:** JPEG, PNG, WebP or PDF, up to 5 MB, one per expense.

## S2.1 App: `purchases`

| Model | Holds |
|---|---|
| `Purchase` | `number` (`P-000001`, sequential per business), `status` (`DRAFT`/`RECEIVED`/`CANCELLED`), optional `supplier`, `reference` (supplier invoice no.), `purchase_date`, `note`, `total`, who created/received/cancelled it and when, `cancel_reason`. Indexes `(business, created_at)`, `(business, purchase_date)`. |
| `PurchaseItem` | `product`, `quantity` > 0, `unit_cost` (as paid), `line_total` (DB check: `quantity × unit_cost`), `batch_number`, `expiry_date`, and `batch` (set on receive). Unique `(purchase, product, batch_number)`. |

**Services (`purchases/services.py`)**, each `@transaction.atomic`:
- **`save_draft()`** creates a draft (its number under the `BusinessSettings` row lock) or replaces a draft's details and lines. Lines are checked:
  - the product is active
  - quantity ≥ 1, cost ≥ 0
  - products that track expiry need a batch number, plus an expiry date when the batch is new
  - an existing batch with a different expiry is refused
  - products without expiry use the DEFAULT batch.
- **`receive_purchase()`**:
  1. Locks the purchase and re-checks every line against the products as they are now. A product may have been archived, or its expiry tracking changed, since the draft was saved.
  2. Per line: `resolve_batch()` → `record_movement(PURCHASE, +qty)` → store the batch on the item → set `product.cost_price`.
  3. Marks the purchase `RECEIVED`.

  Any failure rolls everything back.
- **`cancel_purchase()`**: drafts only, with a reason.

## S2.2 App: `expenses`

| Model | Holds |
|---|---|
| `ExpenseCategory` | `name` (unique per business, case-insensitive), `description`. Every business gets Rent, Salaries & wages, Utilities, Transport, Marketing, Supplies and Other: new ones at registration, existing ones from migration `expenses/0002`. |
| `Expense` | `category`, `amount` > 0, `expense_date` (the date net profit uses), `description`, `paid_to`, `method` (`CASH`), `receipt`, `recorded_by`. Indexes `(business, expense_date)`, `(business, created_at)`. |

**Receipts:**
- **Validation.** PDFs are recognised by their `%PDF-` signature. Images are checked with the Pillow validator used for product images: `validate_product_image` gained optional `max_bytes` / `max_dimension` arguments, and receipts allow up to 10,000 px for phone photos. The size limit is `EXPENSE_RECEIPT_MAX_BYTES`, default 5 MB.
- **Storage.** Files go to `PrivateStorage` under `PRIVATE_MEDIA_ROOT` (default `backend/private_media/`), never under `MEDIA_ROOT`. They have no public URL.
- **Download.** Only through `GET expenses/{id}/receipt/`, which requires `expenses.view` in the owning business. It is sent as an attachment with `Content-Security-Policy: sandbox` and `nosniff`.
- **Writes.** Uploads and removals lock the expense row. A replaced or removed file is deleted only after the change commits.
- **Admin.** The Django admin shows "has receipt" but never the file.

## S2.3 Net profit (FR-16) and dashboard (FR-17)
- `GET sales/summary/` adds two fields:
  - `expenses`: the expenses dated in the range
  - `net_profit`: `gross_profit − expenses`.

  Both are `null` for callers without `expenses.view`.
- The dashboard has a **Today / Last 7 days / This month** selector and live **Expenses** and **Net profit** tiles (only with `expenses.view`). The old placeholder is gone.

## S2.4 Permissions

Defined in `accounts/rbac.py` and data migration `accounts/0006_phase3_purchases_expenses_permissions.py`.

| Codename | Owner | Admin |
|---|---|---|
| `purchases.view` | ✓ | ✓ |
| `purchases.manage` (create, edit, receive, cancel) | ✓ | ✓ |
| `expenses.view` (incl. net profit) | ✓ | ✓ |
| `expenses.manage` (record, edit, receipts, categories) | ✓ | ✓ |
| `expenses.delete` (expenses and categories) | ✓ | |

## S2.5 Endpoints (under `/api/v1/`)

| Endpoint | Permission | Notes |
|---|---|---|
| `GET/POST purchases/` | view / manage | Filters `status`, `supplier`, `date_from`/`date_to` (on `purchase_date`), `number` (`P-000012` or `12`). Search reference, supplier, note. |
| `GET/PUT purchases/{id}/` | view / manage | PUT replaces a draft's details and lines; a received or cancelled purchase is a 400. No PATCH or DELETE. |
| `POST purchases/{id}/receive/` | manage | Returns the purchase with each line's batch. |
| `POST purchases/{id}/cancel/` | manage | `{reason}`. |
| `GET/POST/PATCH/DELETE expense-categories/…` | view / manage / delete | DELETE is a 409 when the category has expenses. |
| `GET/POST/PATCH/DELETE expenses/…` | view / manage / delete | Filters `category`, `date_from`/`date_to` (on `expense_date`). Search description, paid_to. `has_receipt` instead of a file URL. |
| `GET/PUT/DELETE expenses/{id}/receipt/` | view / manage / manage | PUT is multipart `receipt`. |
| `GET expenses/summary/` | view | `?date_from&date_to` (default today): `total`, `count`, `by_category`. |

## S2.6 Frontend
- **`/purchases`:** a list with status, supplier and date filters, and search by number, supplier or reference.
- **`/purchases/new` and `/purchases/:id/edit`:**
  - pick products as on the sale screen
  - quantity and unit cost, prefilled from the product's cost
  - batch number and expiry only for products that track expiry
  - a live total
  - **Save draft** or **Save & receive**.
- **`/purchases/:id`:** lines and batches. On a draft: **Receive** (with confirmation), **Edit** and **Cancel** (needs a reason).
- **`/expenses`:**
  - the period total (this month by default) and a breakdown by category
  - a list with category and date filters
  - an add/edit dialog with receipt upload, view (fetched with the session token) and remove
  - delete only with `expenses.delete`
  - a Categories dialog.
- **Dashboard:** the period selector, plus the Expenses and Net profit tiles.
- **Navigation:** Purchases and Expenses links, each gated by its permission.
- **Shared code:** `lib/purchases.ts` (line checks and totals in cents) and `lib/dates.ts` (period ranges).

## S2.7 Tests

### Backend: `purchases/tests/`
- Drafts: totals, numbering per business, editing, line validation, existing batches.
- Receiving:
  - new and existing batches and the DEFAULT batch
  - `PURCHASE` movements and cost updates
  - sale snapshots before and after a receive
  - a received purchase can't change
  - expiry tracking changed after drafting
  - **a forced failure on the 2nd line rolls back** movements, batches, cost and status
  - NFR-9 reconciliation.
- Cancel; filters; 403 for a role without the codenames; Admin can receive.
- Isolation: 404 on detail, PUT, receive and cancel; another business's supplier and product ids are refused; lists are empty.

### Backend: `expenses/tests/`
- Default categories; category CRUD and the 409.
- Expenses: CRUD, positive amounts, filters, summary by category, Admin can't delete, 403s.
- Receipts:
  - PNG and PDF are accepted and downloaded with safe headers
  - a replaced file is removed
  - fake PDF, text, disguised PHP and oversize files are refused
  - receipts are stored outside `MEDIA_ROOT`
  - viewer permissions.
- Net profit in the sales summary, and `null` without `expenses.view`.
- Isolation: 404 on expense, category and receipt GET/PUT/DELETE; another business's category is refused; lists and summaries are empty.

### Frontend
- Purchase line maths and period ranges.
- Purchases list states.
- Purchase form: the request body, expiry fields shown only when tracked, the server error.
- Purchase detail: receive flow, gating, cancel validation.
- Expenses: list and total, empty and error states, validation, edit with server errors, delete gating and flow.
- Dashboard tiles and period.
- Nav gating.

## S2.8 Known gaps
- [ ] No supplier payments or credit (what the business owes suppliers).
- [ ] A received purchase can't be reversed; correct stock with adjustments.
- [ ] Cost price is "latest cost", not a weighted average.
- [ ] Only cash as an expense method.
- [ ] Receipts are stored on the backend's local disk (`PRIVATE_MEDIA_ROOT`). Production needs private object storage, or a persistent volume and backups.
- [ ] Expense categories can be added and deleted from the UI, but not renamed. The API supports PATCH.
- [ ] Expense edits and deletes aren't audit-logged yet (FR-20, Phase 4).

