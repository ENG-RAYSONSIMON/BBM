import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangleIcon,
  CalendarClockIcon,
  ReceiptIcon,
  ShoppingBagIcon,
  TrendingUpIcon,
  WalletIcon,
} from 'lucide-react'
import type { ComponentType, ReactNode } from 'react'
import { Link } from 'react-router'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { PERMISSIONS } from '@/lib/types'
import type { InventorySummary } from '@/lib/types'

type Icon = ComponentType<{ className?: string }>

// FR-17 sales tiles. Sales and expenses arrive in Phase 3, so these show an
// honest empty state rather than a made-up zero.
const SALES_METRICS: { label: string; icon: Icon; empty: string }[] = [
  { label: "Today's sales", icon: ShoppingBagIcon, empty: 'No sales recorded yet' },
  { label: "Today's profit", icon: TrendingUpIcon, empty: 'Shown once sales are recorded' },
  { label: "Today's expenses", icon: WalletIcon, empty: 'No expenses recorded yet' },
  { label: 'Transactions', icon: ReceiptIcon, empty: 'No transactions yet' },
]

/** The expiry tab closest to the business's warning window. */
function expiryView(days: number) {
  return days <= 7 ? '7' : days <= 30 ? '30' : '60'
}

export function DashboardPage() {
  const { me, can } = useAuth()
  const canSeeStock = can(PERMISSIONS.inventoryView)
  const summary = useQuery({
    queryKey: ['inventory', 'summary'],
    queryFn: () => api<InventorySummary>('/inventory/summary/'),
    enabled: canSeeStock,
  })
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
        {SALES_METRICS.map((metric) => (
          <Tile key={metric.label} label={metric.label} icon={metric.icon} value="—" valueLabel="No data">
            {metric.empty}
          </Tile>
        ))}
        {canSeeStock && (
          <>
            <Tile
              label="Low stock"
              icon={AlertTriangleIcon}
              to="/inventory"
              value={summary.data?.low_stock}
              loading={summary.isPending}
              error={summary.isError}
            >
              {summary.data &&
                (summary.data.out_of_stock > 0
                  ? `${summary.data.out_of_stock} out of stock`
                  : 'Products at or below their alert level')}
            </Tile>
            <Tile
              label="Expiring soon"
              icon={CalendarClockIcon}
              to={`/inventory?view=${expiryView(summary.data?.expiry_warning_days ?? 30)}`}
              value={summary.data?.expiring_soon}
              loading={summary.isPending}
              error={summary.isError}
            >
              {summary.data &&
                (summary.data.expired > 0
                  ? `${summary.data.expired} batches already expired`
                  : `Batches expiring within ${summary.data.expiry_warning_days} days`)}
            </Tile>
          </>
        )}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Products and stock are live</CardTitle>
          <CardDescription>
            Stock levels and alerts above come from your own records. Sales, profit and expenses will
            fill in once sales recording arrives.
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  )
}

function Tile({
  label,
  icon: IconComponent,
  value,
  valueLabel,
  to,
  loading = false,
  error = false,
  children,
}: {
  label: string
  icon: Icon
  value: number | string | undefined
  valueLabel?: string
  to?: string
  loading?: boolean
  error?: boolean
  children?: ReactNode
}) {
  const muted = typeof value !== 'number'
  const card = (
    <Card className={to ? 'hover:bg-muted/50 h-full transition-colors' : 'h-full'}>
      <CardHeader>
        <CardDescription className="flex items-center gap-2">
          <IconComponent className="size-4" />
          {label}
        </CardDescription>
        {loading ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <CardTitle className={muted ? 'text-muted-foreground text-2xl' : 'text-2xl tabular-nums'} aria-label={valueLabel}>
            {error ? '—' : value}
          </CardTitle>
        )}
      </CardHeader>
      <CardContent className="text-muted-foreground text-sm">
        {error ? 'Could not load. Refresh to try again.' : children}
      </CardContent>
    </Card>
  )
  return to ? <Link to={to}>{card}</Link> : card
}
