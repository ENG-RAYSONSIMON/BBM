# Phase 3 — The Money Path (step 1: cash sales and credit)

Covers **FR-11** (atomic sale), **FR-12** (full rollback), **FR-13** (overselling
blocked), **FR-16** (gross profit from snapshotted cost) and **FR-17** (live
dashboard figures) from `docs/BBM_SRS_Summary_Draft.pdf` (v0.2), for cash
sales. Purchases (FR-14), expenses (FR-15) and net profit are the next steps.

Status as of 2026-10-10: implemented, not yet committed.
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
