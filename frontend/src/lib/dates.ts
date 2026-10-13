/** Local calendar date as the API's "YYYY-MM-DD". */
export function isoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export type Period = 'today' | 'week' | 'month'

/** FR-17 date range for a dashboard period, in the shop's local calendar. */
export function periodRange(period: Period, now = new Date()): { date_from?: string; date_to?: string } {
  if (period === 'today') return {} // the server's "today" (Africa/Dar_es_Salaam)
  const from =
    period === 'week'
      ? new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6)
      : new Date(now.getFullYear(), now.getMonth(), 1)
  return { date_from: isoDate(from), date_to: isoDate(now) }
}
