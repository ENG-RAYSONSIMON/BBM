import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import type { StockStatus } from '@/lib/types'

export function StockBadge({ status }: { status: StockStatus }) {
  const { t } = useTranslation()
  if (status === 'in') return null
  return <Badge variant={status === 'out' ? 'destructive' : 'secondary'}>{t(`stock.${status}`)}</Badge>
}

/** Badge for a batch expiry: expired, or expiring within `warnDays`. */
export function ExpiryBadge({ daysLeft, warnDays = 30 }: { daysLeft: number; warnDays?: number }) {
  const { t } = useTranslation()
  if (daysLeft < 0) return <Badge variant="destructive">{t('stock.expired')}</Badge>
  if (daysLeft <= warnDays) {
    return (
      <Badge variant="secondary">
        {daysLeft === 0 ? t('stock.expiresToday') : t('stock.daysLeft', { count: daysLeft })}
      </Badge>
    )
  }
  return null
}
