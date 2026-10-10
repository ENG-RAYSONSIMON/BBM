import { Badge } from '@/components/ui/badge'
import type { PaymentStatus } from '@/lib/types'

const LABELS: Record<PaymentStatus, string> = {
  PAID: 'Paid',
  PARTIAL: 'Part paid',
  UNPAID: 'Unpaid',
  VOID: 'Void',
}

export function PaymentStatusBadge({ status }: { status: PaymentStatus }) {
  const variant = status === 'PAID' ? 'outline' : status === 'VOID' ? 'destructive' : 'secondary'
  return <Badge variant={variant}>{LABELS[status]}</Badge>
}
