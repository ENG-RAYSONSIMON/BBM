import type { Batch, Expense, Paginated, Product, PurchaseDetail, SaleDetail } from '@/lib/types'

export function page<T>(results: T[]): Paginated<T> {
  return { count: results.length, next: null, previous: null, results }
}

export const EMPTY_PAGE = page([])

export function product(overrides: Partial<Product> = {}): Product {
  return {
    id: 'p1',
    name: 'Shea Butter',
    description: '',
    sku: 'SHEA-1',
    barcode: '',
    unit: 'pcs',
    category: null,
    category_detail: null,
    brand: null,
    brand_detail: null,
    supplier: null,
    supplier_detail: null,
    selling_price: '15000.00',
    cost_price: '9000.00',
    reorder_level: null,
    tracks_expiry: true,
    image: null,
    is_active: true,
    stock_on_hand: 3,
    threshold: 5,
    stock_status: 'low',
    is_low_stock: true,
    nearest_expiry: '2026-12-31',
    created_at: '2026-10-01T08:00:00Z',
    updated_at: '2026-10-01T08:00:00Z',
    ...overrides,
  }
}

export function batch(overrides: Partial<Batch> = {}): Batch {
  return {
    id: 'b1',
    product: 'p1',
    batch_number: 'L-001',
    expiry_date: '2026-12-31',
    received_on: '2026-10-01',
    stock_on_hand: 3,
    created_at: '2026-10-01T08:00:00Z',
    ...overrides,
  }
}

/** Empty option lists for the category/brand/supplier dropdowns. */
export const REF_ROUTES = {
  'GET /categories/': { status: 200, body: EMPTY_PAGE },
  'GET /brands/': { status: 200, body: EMPTY_PAGE },
  'GET /suppliers/': { status: 200, body: EMPTY_PAGE },
}

export function sale(overrides: Partial<SaleDetail> = {}): SaleDetail {
  return {
    id: 's1',
    number: 7,
    receipt_number: 'S-000007',
    status: 'COMPLETED',
    customer: 'c1',
    customer_name: 'Mama Asha',
    customer_phone: '0712000000',
    sold_by: 'u1',
    sold_by_name: 'Amina',
    subtotal: '30000.00',
    discount_total: '0.00',
    total: '30000.00',
    cost_total: '18000.00',
    gross_profit: '12000.00',
    amount_paid: '10000.00',
    balance: '20000.00',
    payment_status: 'PARTIAL',
    note: '',
    created_at: '2026-10-10T08:00:00Z',
    items: [],
    payments: [],
    voided_at: null,
    voided_by: null,
    voided_by_name: '',
    void_reason: '',
    ...overrides,
  }
}

export function purchase(overrides: Partial<PurchaseDetail> = {}): PurchaseDetail {
  return {
    id: 'pu1',
    number: 3,
    purchase_number: 'P-000003',
    status: 'DRAFT',
    supplier: 'sup1',
    supplier_name: 'Dar Cosmetics',
    reference: 'INV-77',
    purchase_date: '2026-10-12',
    note: '',
    total: '75000.00',
    item_count: 1,
    created_by: 'u1',
    created_by_name: 'Amina',
    received_at: null,
    created_at: '2026-10-12T08:00:00Z',
    items: [
      {
        id: 'pi1',
        product: 'p1',
        product_name: 'Shea Butter',
        tracks_expiry: true,
        quantity: 10,
        unit_cost: '7500.00',
        line_total: '75000.00',
        batch_number: 'SB-01',
        expiry_date: '2027-06-30',
        batch: null,
      },
    ],
    received_by: null,
    received_by_name: '',
    cancelled_at: null,
    cancelled_by: null,
    cancelled_by_name: '',
    cancel_reason: '',
    ...overrides,
  }
}

export function expense(overrides: Partial<Expense> = {}): Expense {
  return {
    id: 'e1',
    category: 'cat-rent',
    category_name: 'Rent',
    amount: '50000.00',
    expense_date: '2026-10-12',
    description: 'October rent',
    paid_to: 'Landlord',
    method: 'CASH',
    has_receipt: false,
    recorded_by: 'u1',
    recorded_by_name: 'Amina',
    created_at: '2026-10-12T08:00:00Z',
    updated_at: '2026-10-12T08:00:00Z',
    ...overrides,
  }
}

export const EXPENSE_CATEGORIES = page([
  { id: 'cat-rent', name: 'Rent', description: '', created_at: '', updated_at: '' },
  { id: 'cat-transport', name: 'Transport', description: '', created_at: '', updated_at: '' },
])
