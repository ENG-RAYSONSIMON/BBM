import type { Batch, Paginated, Product } from '@/lib/types'

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
