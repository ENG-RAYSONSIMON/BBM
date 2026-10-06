const tzs = new Intl.NumberFormat('en-TZ', {
  style: 'currency',
  currency: 'TZS',
  maximumFractionDigits: 0,
})

/** "TSh 15,000". Accepts the API's decimal strings. */
export function formatTZS(value: string | number): string {
  const amount = typeof value === 'string' ? Number(value) : value
  return Number.isFinite(amount) ? tzs.format(amount) : '—'
}

const dateFormat = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
const dateTimeFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** API dates ("2026-10-06") are calendar dates: format without time-zone shifts. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const [y, m, d] = value.slice(0, 10).split('-').map(Number)
  return dateFormat.format(new Date(y, m - 1, d))
}

export function formatDateTime(value: string): string {
  return dateTimeFormat.format(new Date(value))
}

/** "+5" / "−3" with a real minus sign. */
export function formatQuantity(quantity: number): string {
  return quantity > 0 ? `+${quantity}` : `−${Math.abs(quantity)}`
}
