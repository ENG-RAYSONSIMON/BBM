import { Badge } from '@/components/ui/badge'
import type { StockStatus } from '@/lib/types'

const LABELS: Record<StockStatus, string> = { out: 'Out of stock', low: 'Low stock', in: 'In stock' }

export function StockBadge({ status }: { status: StockStatus }) {
  if (status === 'in') return null
  return <Badge variant={status === 'out' ? 'destructive' : 'secondary'}>{LABELS[status]}</Badge>
}

/** Badge for a batch expiry: expired, or expiring within `warnDays`. */
export function ExpiryBadge({ daysLeft, warnDays = 30 }: { daysLeft: number; warnDays?: number }) {
  if (daysLeft < 0) return <Badge variant="destructive">Expired</Badge>
  if (daysLeft <= warnDays) {
    return <Badge variant="secondary">{daysLeft === 0 ? 'Expires today' : `${daysLeft} days left`}</Badge>
  }
  return null
}
