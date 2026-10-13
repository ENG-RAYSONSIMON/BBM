import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import type { PaymentStatus } from '@/lib/types'

export function PaymentStatusBadge({ status }: { status: PaymentStatus }) {
  const { t } = useTranslation()
  const variant = status === 'PAID' ? 'outline' : status === 'VOID' ? 'destructive' : 'secondary'
  return <Badge variant={variant}>{t(`sales.status_${status}`)}</Badge>
}
