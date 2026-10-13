import { currentLanguage } from '@/i18n'

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

const DATE_LOCALES = { en: 'en-GB', sw: 'sw-TZ' } as const

const dateFormats = new Map<string, Intl.DateTimeFormat>()

/** Date formatters follow the UI language ("13 Oct 2026" / "13 Okt 2026"). */
function formatter(withTime: boolean): Intl.DateTimeFormat {
  const language = currentLanguage()
  const key = `${language}:${withTime}`
  let format = dateFormats.get(key)
  if (!format) {
    format = new Intl.DateTimeFormat(DATE_LOCALES[language], {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
    })
    dateFormats.set(key, format)
  }
  return format
}

/** API dates ("2026-10-06") are calendar dates: format without time-zone shifts. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const [y, m, d] = value.slice(0, 10).split('-').map(Number)
  return formatter(false).format(new Date(y, m - 1, d))
}

export function formatDateTime(value: string): string {
  return formatter(true).format(new Date(value))
}

/** "+5" / "−3" with a real minus sign. */
export function formatQuantity(quantity: number): string {
  return quantity > 0 ? `+${quantity}` : `−${Math.abs(quantity)}`
}
