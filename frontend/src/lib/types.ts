// Response shapes of the BBM API (see /api/docs/).

export type User = {
  id: string
  email: string
  first_name: string
  last_name: string
  phone: string
}

export type Business = {
  id: string
  name: string
  tin: string
  phone: string
  email: string
  address: string
  currency: string
}

export type AuthPayload = {
  access: string
  refresh: string
  user: User
  business: Business
  role: string
}

export type Me = {
  user: User
  business: Business
  role: string
  permissions: string[]
}

export type BusinessChoice = { id: string; name: string }

export type BusinessSettings = {
  low_stock_threshold: number
  expiry_warning_days: number
  tax_rate: string
  loyalty_enabled: boolean
}

export const PERMISSIONS = {
  settingsView: 'settings.view',
  settingsManage: 'settings.manage',
  catalogView: 'catalog.view',
  catalogManage: 'catalog.manage',
  catalogDelete: 'catalog.delete',
  inventoryView: 'inventory.view',
  inventoryAdjust: 'inventory.adjust',
  salesView: 'sales.view',
  salesCreate: 'sales.create',
  salesVoid: 'sales.void',
} as const

/** DRF page-number pagination envelope. */
export type Paginated<T> = {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type Ref = { id: string; name: string }

export type Category = {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
}

export type Brand = Category

export type Supplier = {
  id: string
  name: string
  contact_person: string
  phone: string
  email: string
  address: string
  notes: string
  created_at: string
  updated_at: string
}

export type StockStatus = 'out' | 'low' | 'in'

export type Product = {
  id: string
  name: string
  description: string
  sku: string
  barcode: string
  unit: string
  category: string | null
  category_detail: Ref | null
  brand: string | null
  brand_detail: Ref | null
  supplier: string | null
  supplier_detail: Ref | null
  /** Decimal strings, e.g. "15000.00". */
  selling_price: string
  cost_price: string
  reorder_level: number | null
  tracks_expiry: boolean
  image: string | null
  is_active: boolean
  stock_on_hand: number
  threshold: number
  stock_status: StockStatus
  is_low_stock: boolean
  nearest_expiry: string | null
  created_at: string
  updated_at: string
}

export type Batch = {
  id: string
  product: string
  batch_number: string
  expiry_date: string | null
  received_on: string | null
  stock_on_hand: number
  created_at: string
}

export type MovementType = 'PURCHASE' | 'SALE' | 'ADJUSTMENT' | 'DAMAGE' | 'EXPIRY' | 'TRANSFER' | 'RETURN'

export type StockMovement = {
  id: string
  product: string
  product_name: string
  batch: string
  batch_number: string
  movement_type: MovementType
  quantity: number
  reason: string
  created_by: string
  created_by_name: string
  created_at: string
}

export type ExpiringBatch = {
  id: string
  product: string
  product_name: string
  batch_number: string
  expiry_date: string
  stock_on_hand: number
  days_left: number
}

export type InventorySummary = {
  low_stock: number
  out_of_stock: number
  expiring_soon: number
  expired: number
  expiry_warning_days: number
}

// ---- Phase 3: sales --------------------------------------------------------
// Money fields are decimal strings ("12000.00"), like product prices.

export type Customer = {
  id: string
  name: string
  phone: string
  notes: string
  total_bought: string
  amount_paid: string
  /** Still owed on credit sales. */
  balance: string
  created_at: string
  updated_at: string
}

export type PaymentStatus = 'PAID' | 'PARTIAL' | 'UNPAID' | 'VOID'

export type Sale = {
  id: string
  number: number
  receipt_number: string
  status: 'COMPLETED' | 'VOID'
  customer: string | null
  customer_name: string | null
  customer_phone: string | null
  sold_by: string
  sold_by_name: string
  subtotal: string
  discount_total: string
  total: string
  cost_total: string
  gross_profit: string
  amount_paid: string
  balance: string
  payment_status: PaymentStatus
  note: string
  created_at: string
}

export type SaleItem = {
  id: string
  product: string
  product_name: string
  quantity: number
  unit_price: string
  discount: string
  line_total: string
  unit_cost: string
  line_cost: string
  allocations: { batch: string; batch_number: string; expiry_date: string | null; quantity: number }[]
}

export type Payment = {
  id: string
  kind: 'PAYMENT' | 'REFUND'
  method: 'CASH'
  amount: string
  amount_received: string
  change_given: string
  received_by: string
  received_by_name: string
  note: string
  created_at: string
}

export type SaleDetail = Sale & {
  items: SaleItem[]
  payments: Payment[]
  voided_at: string | null
  voided_by: string | null
  voided_by_name: string
  void_reason: string
}

export type SalesSummary = {
  date_from: string
  date_to: string
  sales_count: number
  revenue: string
  discounts: string
  cogs: string
  gross_profit: string
  /** Payments − refunds in the range. */
  cash_collected: string
  /** Still owed on all sales, all time. */
  outstanding_credit: string
}
