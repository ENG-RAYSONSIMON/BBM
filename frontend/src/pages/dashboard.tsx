import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangleIcon,
  BanknoteIcon,
  CalendarClockIcon,
  HandCoinsIcon,
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
import { formatTZS } from '@/lib/format'
import { PERMISSIONS } from '@/lib/types'
import type { InventorySummary, SalesSummary } from '@/lib/types'

type Icon = ComponentType<{ className?: string }>

/** The expiry tab closest to the business's warning window. */
function expiryView(days: number) {
  return days <= 7 ? '7' : days <= 30 ? '30' : '60'
}

export function DashboardPage() {
  const { me, can } = useAuth()
  const canSeeStock = can(PERMISSIONS.inventoryView)
  const canSeeSales = can(PERMISSIONS.salesView)
  // FR-17: today's figures (the server's "today" is Africa/Dar_es_Salaam).
  const sales = useQuery({
    queryKey: ['sales', 'summary', 'today'],
    queryFn: () => api<SalesSummary>('/sales/summary/'),
    enabled: canSeeSales,
  })
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
        {canSeeSales && (
          <>
            <Tile
              label="Today's sales"
              icon={ShoppingBagIcon}
              to="/sales"
              value={sales.data && formatTZS(sales.data.revenue)}
              loading={sales.isPending}
              error={sales.isError}
            >
              {sales.data &&
                (sales.data.sales_count === 0
                  ? 'No sales yet today'
                  : `${sales.data.sales_count} ${sales.data.sales_count === 1 ? 'sale' : 'sales'}`)}
            </Tile>
            <Tile
              label="Today's profit"
              icon={TrendingUpIcon}
              value={sales.data && formatTZS(sales.data.gross_profit)}
              loading={sales.isPending}
              error={sales.isError}
            >
              {sales.data && `Sales minus cost of goods (${formatTZS(sales.data.cogs)})`}
            </Tile>
            <Tile
              label="Cash collected today"
              icon={BanknoteIcon}
              value={sales.data && formatTZS(sales.data.cash_collected)}
              loading={sales.isPending}
              error={sales.isError}
            >
              Cash received, including debt repayments, less refunds
            </Tile>
            <Tile
              label="Owed by customers"
              icon={HandCoinsIcon}
              to="/customers?owes=true"
              value={sales.data && formatTZS(sales.data.outstanding_credit)}
              loading={sales.isPending}
              error={sales.isError}
            >
              Unpaid balances on credit sales
            </Tile>
          </>
        )}
        <Tile label="Today's expenses" icon={WalletIcon} value={undefined} valueLabel="No data">
          Expense tracking comes next
        </Tile>
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
          <CardTitle>Figures are live</CardTitle>
          <CardDescription>
            Sales, profit, cash and stock above come straight from your records. Profit counts a sale on the
            day it is made, even when the customer pays later; net profit arrives with expenses.
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
  const muted = value === undefined
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
            {error || value === undefined ? '—' : value}
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
