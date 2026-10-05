import {
  AlertTriangleIcon,
  CalendarClockIcon,
  ReceiptIcon,
  ShoppingBagIcon,
  TrendingUpIcon,
  WalletIcon,
} from 'lucide-react'
import type { ComponentType } from 'react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/lib/auth-context'

type Metric = {
  label: string
  icon: ComponentType<{ className?: string }>
  empty: string
}

// FR-17 dashboard tiles. There are no sales, expenses or products yet, so each
// tile shows an honest empty state rather than a made-up zero.
const METRICS: Metric[] = [
  { label: "Today's sales", icon: ShoppingBagIcon, empty: 'No sales recorded yet' },
  { label: "Today's profit", icon: TrendingUpIcon, empty: 'Shown once sales are recorded' },
  { label: "Today's expenses", icon: WalletIcon, empty: 'No expenses recorded yet' },
  { label: 'Transactions', icon: ReceiptIcon, empty: 'No transactions yet' },
  { label: 'Low stock', icon: AlertTriangleIcon, empty: 'Add products to track stock' },
  { label: 'Expiring soon', icon: CalendarClockIcon, empty: 'Add products to track expiry' },
]

export function DashboardPage() {
  const { me } = useAuth()
  if (!me) return null

  const name = me.user.first_name || me.user.email

  return (
    <div className="mx-auto grid max-w-6xl gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Welcome, {name}</h1>
        <p className="text-muted-foreground">
          {me.business.name} · {me.role}
        </p>
      </div>

      <section aria-label="Today at a glance" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {METRICS.map((metric) => (
          <Card key={metric.label}>
            <CardHeader>
              <CardDescription className="flex items-center gap-2">
                <metric.icon className="size-4" />
                {metric.label}
              </CardDescription>
              <CardTitle className="text-muted-foreground text-2xl" aria-label="No data">
                —
              </CardTitle>
            </CardHeader>
            <CardContent className="text-muted-foreground text-sm">{metric.empty}</CardContent>
          </Card>
        ))}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Your workspace is ready</CardTitle>
          <CardDescription>
            Products, stock and sales tracking are on the way. As they arrive, the figures above
            will fill in automatically from your own records.
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  )
}
