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

export type MovementType = 'PURCHASE' | 'SALE' | 'ADJUSTMENT' | 'DAMAGE' | 'EXPIRY' | 'TRANSFER'

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
