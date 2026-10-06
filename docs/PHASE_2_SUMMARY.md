# Phase 2 — Catalog & Inventory

Covers **FR-6** (products with category, brand, supplier, batch and expiry),
**FR-7/FR-8** (stock ledger; stock is always derived), **FR-9** (low-stock and
expiry views) and **FR-10** (validated product images) from
`docs/BBM_SRS_Summary_Draft.pdf` (v0.2), plus NFR-5, NFR-7, NFR-8, NFR-9 and
NFR-10 for the new endpoints.

Status as of 2026-10-06: implemented. Backend: 120 tests (61 from Phase 1, 59
new), schema validates with `--fail-on-warn`. Frontend: 31 Vitest tests.

Decisions taken with the product owner:
- **Stock per batch.** Every movement belongs to a batch.
- **Manual adjustments** put stock in until Phase 3 purchases.
- **Local media folder** for images; object storage later.

---

## 1. Apps

| App | Holds |
|---|---|
| `catalog` | `Category`, `Brand`, `Supplier`, `Product`, `ProductBatch`; CRUD views, product image upload, image validation (`validators.py`). |
| `inventory` | `StockMovement` (the ledger); `services.py` (writes and derived-stock queries); batch, adjustment and alert endpoints. |
| `core` (added) | `TenantModel.check_same_business()`, `TenantModelViewSet` (scoped queryset, `ProtectedError` → 409), `DefaultPagination`. |

All new models are `TenantModel`s.

## 2. Models

### Catalog
- **`Category`, `Brand`**: `name` (unique per business, case-insensitive: `UniqueConstraint("business", Lower("name"))`), `description`.
- **`Supplier`**: `name` (same rule), `contact_person`, `phone`, `email`, `address`, `notes`.
- **`Product`**:
  - `name`, `description`, `unit` (default `pcs`)
  - `sku`, `barcode`: each unique per business when not blank (conditional constraint)
  - `category`, `brand`, `supplier`: nullable FKs, `PROTECT`
  - `selling_price`, `cost_price`: Decimal(12,2), with a DB check that both are ≥ 0
  - `reorder_level`: nullable; null uses `BusinessSettings.low_stock_threshold`
  - `tracks_expiry`, `image`, `is_active`
  - `save()` refuses FKs that point at another business (`check_same_business`).
  - **There is no stock column.**
- **`ProductBatch`**:
  - `product` (FK `PROTECT`), `batch_number` (unique per product), `expiry_date`, `received_on`
  - index `(business, expiry_date)`
  - Products with `tracks_expiry = False` use one automatic `DEFAULT` batch.

### Inventory
- **`StockMovement`**:
  - `product`, `batch`, `movement_type`, signed `quantity`, `reason`, `created_by`
  - DB constraints:
    - `quantity <> 0`
    - `SALE`, `DAMAGE` and `EXPIRY` must be negative
    - `PURCHASE` must be positive
  - Indexes `(business, created_at)` (NFR-8) and `(business, product, batch)`.
  - **Append-only:**
    - `save()` on an existing row raises `LedgerImmutable`
    - a `pre_delete` receiver raises on any delete, including QuerySet deletes
    - the admin view is read-only
    - the API has no update or delete routes.
  - `save()` also checks that the batch belongs to the product and that both are in the same business.

## 3. Stock service (`inventory/services.py`)
- **`record_movement()`** is the only way stock changes. It:
  - runs in `@transaction.atomic`
  - locks the batch row (`select_for_update`)
  - refuses to take a batch below 0 (`InsufficientStock`).
- **`resolve_batch()`** returns the batch a movement applies to: a given batch, an existing batch found by number (its expiry must match), a new batch (which needs an expiry date when the product tracks expiry), or `DEFAULT`.
- **`with_batch_stock()` / `with_product_stock()`** add these annotations, computed by SQL subqueries over the ledger:
  - `stock_on_hand`
  - `threshold` (`reorder_level`, or the business setting via a scoped subquery)
  - `stock_status` (`out` / `low` / `in`)
  - `is_low_stock` (includes out of stock)
  - `nearest_expiry` (earliest expiry among batches that still hold stock).
- **`expiring_batches()`** and **`inventory_summary()`** back the alert endpoints.
- `TIME_ZONE` is now `Africa/Dar_es_Salaam`, so "today" in expiry windows is Tanzanian local time. Datetimes are still stored in UTC.

## 4. Permissions
New codenames in `accounts/rbac.py`, plus data migration `accounts/0004_phase2_permissions.py`:

| Codename | Owner | Admin |
|---|---|---|
| `catalog.view` | ✓ | ✓ |
| `catalog.manage` (create/edit/archive, images) | ✓ | ✓ |
| `catalog.delete` | ✓ | |
| `inventory.view` | ✓ | ✓ |
| `inventory.adjust` (adjustments, batches) | ✓ | ✓ |

## 5. Endpoints (under `/api/v1/`)
All lists are paginated: `?page=`, and `?page_size=` up to 100, default 25.

| Endpoint | Notes |
|---|---|
| `categories/`, `brands/`, `suppliers/` | CRUD with `?search=` and `?ordering=`. A duplicate name is a 400. Deleting a row still in use is a 409. |
| `products/` | CRUD with filters `category`, `brand`, `supplier`, `is_active`, `tracks_expiry`, `stock_status=low\|out\|in`; search name/SKU/barcode; ordering. Responses include the derived stock fields. DELETE is a 409 if the product has movements (archive with `is_active=false` instead); otherwise its empty batches and image are removed too. `tracks_expiry` is locked once the product has batches. |
| `products/{id}/image/` | PUT (multipart, field `image`) and DELETE. Requires `catalog.manage`. |
| `products/{id}/batches/` | GET and POST. Batch numbers are unique per product (case-insensitive), and expiry is required when the product tracks it. |
| `batches/{id}/` | GET and PATCH (`batch_number`, `expiry_date`). |
| `stock-movements/` | GET with filters `product`, `batch`, `movement_type`, `date_from`, `date_to` and search. POST is a manual adjustment: `movement_type` is `ADJUSTMENT`/`DAMAGE`/`EXPIRY`, `quantity` is signed, `reason` is required, plus either `batch`, or `batch_number` + `expiry_date` for a new batch. |
| `inventory/low-stock/` | Active products at or below their threshold, lowest stock first. |
| `inventory/expiring/` | `?within=1–365` (default: the business's `expiry_warning_days`) or `?expired=true`. Only batches that still hold stock. Each row includes `days_left`. |
| `inventory/summary/` | `low_stock`, `out_of_stock`, `expiring_soon`, `expired`, `expiry_warning_days`. |

## 6. Images (FR-10, NFR-5)
- `catalog/validators.py` reads the real format with Pillow and ignores the filename and the browser's content type. It allows JPEG, PNG and WebP; the limit is 2 MB (env `PRODUCT_IMAGE_MAX_BYTES`) and 4000×4000 px, and `verify()` catches corrupt files.
- Files are saved as `products/<business_id>/<random>.<ext>` under `MEDIA_ROOT` (`backend/media`, gitignored). Replacing or removing an image deletes the old file.
- Django serves `/media/` only when `DEBUG`.

## 7. Frontend
- **Pages:**
  - `/products`: search, filters in the URL, table on desktop / cards on mobile
  - `/products/new` and `/products/:id/edit`: the form, with an image picker that checks type and size in the browser first
  - `/products/:id`: details, batches with expiry badges, paginated stock history, the **Adjust stock** dialog, archive/restore, delete
  - `/inventory`: tabs for low stock, ≤7/30/60 days and expired
  - `/catalog`: categories, brands and suppliers, with create/edit dialogs and delete confirmation.
- **Dashboard:** the Low stock and Expiring tiles show live counts (with `inventory.view`) and link to the matching alert tab. The sales tiles stay empty until Phase 3.
- **Navigation** only shows pages the role may open.
- **Shared code:**
  - `components/data-list.tsx`: loading, empty and error states plus pagination (NFR-10)
  - `lib/use-list-params.ts`: list state kept in the URL
  - `components/confirm-dialog.tsx`: in-app confirmations
  - `lib/format.ts`: TZS, dates, quantities.

## 8. Tests
- **Backend:**
  - `catalog/tests/test_models.py`: uniqueness, cross-tenant FKs, price checks
  - `catalog/tests/test_api.py`: CRUD, permissions, filters, pagination, 409s
  - `catalog/tests/test_images.py`: valid image, real format, replace and delete, fake file, GIF, size and dimension limits
  - `inventory/tests/test_ledger.py`: immutability, sign constraints, per-batch sums, no negative stock, NFR-9 reconciliation over 60 random movements
  - `inventory/tests/test_api.py`: adjustments, batches, alerts, summary
  - `inventory/tests/test_isolation.py` (NFR-7): 404 on every detail, update and delete route; another business's IDs refused as references; lists empty for the other business.
- **Frontend:** products list states, product form validation and server errors, image pre-check, adjust-stock dialog, nav permissions, formatters.

## 9. Known gaps
- [ ] `QuerySet.update()` and `bulk_create()` on `StockMovement` bypass the immutability and tenant checks, which only run in `save()`. Code review is the only guard; DB triggers could be added before going live.
- [ ] Uploaded media is served by Django only in DEBUG. Production needs object storage (`STORAGES` / django-storages) or nginx in front. Image URLs aren't authenticated; the random file names are the only protection.
- [ ] `TRANSFER` is reserved; there are no stock locations yet.
- [ ] Overselling override (FR-13) and FEFO batch consumption arrive with sales in Phase 3.
- [ ] Batch cost isn't stored. Phase 3 COGS will snapshot the product's `cost_price` at sale time, as the SRS says.
- [ ] The main JS chunk is about 600 kB. Lazy-load routes once Phase 3 adds more pages.
- [ ] Media files written by the backend container are owned by root on the host (bind mount).
