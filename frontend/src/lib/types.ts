// Response shapes of the BBM API (see /api/docs/).

export type User = {
  id: string
  email: string
  first_name: string
  last_name: string
  phone: string
  /** On a temporary password: the app only lets them choose a new one. */
  must_change_password: boolean
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
  purchasesView: 'purchases.view',
  purchasesManage: 'purchases.manage',
  expensesView: 'expenses.view',
  expensesManage: 'expenses.manage',
  expensesDelete: 'expenses.delete',
  auditView: 'audit.view',
  reportsView: 'reports.view',
  reportsExport: 'reports.export',
  salesViewAll: 'sales.view_all',
  paymentsCreate: 'payments.create',
  financeView: 'finance.view',
  staffManage: 'staff.manage',
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
  /** Left out without finance.view. */
  cost_price?: string
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
  /** Cost and profit are left out without finance.view. */
  cost_total?: string
  gross_profit?: string
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
  /** Left out without finance.view. */
  unit_cost?: string
  line_cost?: string
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
  /** Null without finance.view. */
  cogs: string | null
  gross_profit: string | null
  /** Payments − refunds in the range. */
  cash_collected: string
  /** Still owed on all sales, all time. */
  outstanding_credit: string
  /** Expenses dated in the range; null without expenses.view. */
  expenses: string | null
  /** Gross profit − expenses; null without expenses.view and finance.view. */
  net_profit: string | null
}

// ---- Phase 3 step 2: purchases and expenses --------------------------------

export type PurchaseStatus = 'DRAFT' | 'RECEIVED' | 'CANCELLED'

export type Purchase = {
  id: string
  number: number
  purchase_number: string
  status: PurchaseStatus
  supplier: string | null
  supplier_name: string | null
  reference: string
  purchase_date: string
  note: string
  total: string
  item_count: number
  created_by: string
  created_by_name: string
  received_at: string | null
  created_at: string
}

export type PurchaseItem = {
  id: string
  product: string
  product_name: string
  tracks_expiry: boolean
  quantity: number
  unit_cost: string
  line_total: string
  batch_number: string
  expiry_date: string | null
  /** Set once the purchase is received. */
  batch: string | null
}

export type PurchaseDetail = Purchase & {
  items: PurchaseItem[]
  received_by: string | null
  received_by_name: string
  cancelled_at: string | null
  cancelled_by: string | null
  cancelled_by_name: string
  cancel_reason: string
}

export type ExpenseCategory = {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
}

export type Expense = {
  id: string
  category: string
  category_name: string
  amount: string
  expense_date: string
  description: string
  paid_to: string
  method: 'CASH'
  has_receipt: boolean
  recorded_by: string
  recorded_by_name: string
  created_at: string
  updated_at: string
}

export type ExpensesSummary = {
  date_from: string
  date_to: string
  total: string
  count: number
  by_category: { category: string; category_name: string; total: string; count: number }[]
}

export const AUDIT_ACTIONS = [
  'DELETE',
  'SETTINGS_CHANGE',
  'ROLE_CHANGE',
  'SALE_VOID',
  'PURCHASE_CANCEL',
  'EXPENSE_CHANGE',
  'EXPORT',
  'STAFF_ADD',
  'STAFF_CHANGE',
  'STAFF_PASSWORD_RESET',
] as const

export type AuditAction = (typeof AUDIT_ACTIONS)[number]

/** FR-20 audit entry. `changes` is {field: [old, new]} or details such as a reason. */
export type AuditLogEntry = {
  id: string
  action: AuditAction
  actor: string | null
  actor_name: string
  target_type: string
  target_id: string | null
  target_label: string
  changes: Record<string, unknown>
  ip_address: string | null
  created_at: string
}

// ---- FR-18 reports ----

export const REPORT_PERIODS = ['day', 'week', 'month', 'year'] as const
export type ReportPeriod = (typeof REPORT_PERIODS)[number]

type PeriodReport<Row, Totals> = {
  period: ReportPeriod
  date_from: string
  date_to: string
  rows: Row[]
  totals: Totals
}

export type SalesReportRow = {
  /** First day of the period (weeks start on Monday). */
  period: string
  sales_count: number
  revenue: string
  discounts: string
  cogs: string
  gross_profit: string
  cash_collected: string
}
export type SalesReport = PeriodReport<SalesReportRow, Omit<SalesReportRow, 'period'>>

export type ProfitReportRow = {
  period: string
  revenue: string
  cogs: string
  gross_profit: string
  expenses: string
  net_profit: string
}
export type ProfitReport = PeriodReport<ProfitReportRow, Omit<ProfitReportRow, 'period'>>

export type ExpensesReportRow = {
  period: string
  category: string
  category_name: string
  count: number
  total: string
}
export type ExpensesReport = PeriodReport<ExpensesReportRow, { count: number; total: string }>

export type StockValuationRow = {
  product: string
  name: string
  sku: string
  category_name: string
  unit: string
  is_active: boolean
  stock_on_hand: number
  cost_price: string
  selling_price: string
  cost_value: string
  retail_value: string
}
export type StockValuationReport = {
  as_of: string
  rows: StockValuationRow[]
  totals: { product_count: number; stock_on_hand: number; cost_value: string; retail_value: string }
}

export type ExpiryReportRow = {
  batch: string
  product: string
  name: string
  sku: string
  batch_number: string
  expiry_date: string
  /** Negative once expired. */
  days_left: number
  status: 'expired' | 'expiring'
  is_active: boolean
  stock_on_hand: number
  cost_price: string
  cost_value: string
}
export type ExpiryReport = {
  as_of: string
  within_days: number
  rows: ExpiryReportRow[]
  totals: { batch_count: number; stock_on_hand: number; cost_value: string; expired_value: string }
}

// ---- FR-19 notifications ----

export type NotificationKind = 'LOW_STOCK' | 'EXPIRING' | 'EXPIRED'

/** Text is rendered from `kind` + `params` in the reader's language. */
export type AppNotification = {
  id: string
  kind: NotificationKind
  channel: 'IN_APP' | 'EMAIL' | 'SMS' | 'WHATSAPP'
  params: {
    product?: string
    name?: string
    stock?: number
    unit?: string
    threshold?: number
    batch_number?: string
    expiry_date?: string
    days?: number
  }
  target_type: string
  target_id: string | null
  is_read: boolean
  resolved_at: string | null
  created_at: string
}

// ---- Staff ----

/** A person's membership of the business; `id` is the membership id. */
export type StaffMember = {
  id: string
  email: string
  first_name: string
  last_name: string
  phone: string
  role: string
  role_name: string
  is_active: boolean
  /** Still on a temporary password. */
  must_change_password: boolean
  last_login: string | null
  is_you: boolean
  /** Whether you may change their role, access or password. */
  can_manage: boolean
  created_at: string
}

export type Role = {
  id: string
  name: string
  is_system: boolean
  permissions: string[]
  /** Whether you may give this role. */
  assignable: boolean
}
