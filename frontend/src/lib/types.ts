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
} as const
