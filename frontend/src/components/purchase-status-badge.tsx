import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import type { PurchaseStatus } from '@/lib/types'

export function PurchaseStatusBadge({ status }: { status: PurchaseStatus }) {
  const { t } = useTranslation()
  const variant = status === 'RECEIVED' ? 'outline' : status === 'CANCELLED' ? 'destructive' : 'secondary'
  return <Badge variant={variant}>{t(`purchases.status_${status}`)}</Badge>
}
