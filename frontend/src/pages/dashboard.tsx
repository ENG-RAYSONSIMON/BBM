import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangleIcon,
  BanknoteIcon,
  CalendarClockIcon,
  CoinsIcon,
  HandCoinsIcon,
  ShoppingBagIcon,
  TrendingUpIcon,
  WalletIcon,
} from 'lucide-react'
import { useState } from 'react'
import type { ComponentType, ReactNode } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { periodRange } from '@/lib/dates'
import type { Period } from '@/lib/dates'
import { formatTZS } from '@/lib/format'
import { PERMISSIONS } from '@/lib/types'
import type { InventorySummary, SalesSummary } from '@/lib/types'
import { toQuery } from '@/lib/use-list-params'

type Icon = ComponentType<{ className?: string }>

// Labels are keys under `dashboard` (e.g. dashboard.week, dashboard.sales_week).
const PERIODS: Period[] = ['today', 'week', 'month']

/** The expiry tab closest to the business's warning window. */
function expiryView(days: number) {
  return days <= 7 ? '7' : days <= 30 ? '30' : '60'
}

export function DashboardPage() {
  const { me, can } = useAuth()
  const { t } = useTranslation()
  const canSeeStock = can(PERMISSIONS.inventoryView)
  const canSeeSales = can(PERMISSIONS.salesView)
  const canSeeExpenses = can(PERMISSIONS.expensesView)
  const [period, setPeriod] = useState<Period>('today')
  // FR-17: figures for the chosen period, straight from live queries.
  const sales = useQuery({
    queryKey: ['sales', 'summary', period],
    queryFn: () => api<SalesSummary>(`/sales/summary/${toQuery(periodRange(period))}`),
    enabled: canSeeSales,
    placeholderData: (previous) => previous,
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
        <h1 className="text-2xl font-semibold tracking-tight">{t('dashboard.welcome', { name })}</h1>
        <p className="text-muted-foreground">
          {me.business.name} · {me.role}
        </p>
      </div>

      {canSeeSales && (
        <div className="flex flex-wrap gap-2" role="group" aria-label={t('dashboard.period')}>
          {PERIODS.map((p) => (
            <Button
              key={p}
              size="sm"
              variant={period === p ? 'default' : 'outline'}
              aria-pressed={period === p}
              onClick={() => setPeriod(p)}
            >
              {t(`dashboard.${p}`)}
            </Button>
          ))}
        </div>
      )}

      <section aria-label={t('dashboard.atAGlance', { period: t(`dashboard.${period}`) })} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {canSeeSales && (
          <>
            <Tile
              label={t(`dashboard.sales_${period}`)}
              icon={ShoppingBagIcon}
              to="/sales"
              value={sales.data && formatTZS(sales.data.revenue)}
              loading={sales.isPending}
              error={sales.isError}
            >
              {sales.data &&
                (sales.data.sales_count === 0
                  ? t(period === 'today' ? 'dashboard.noSalesToday' : 'dashboard.noSalesPeriod')
                  : t('dashboard.salesCount', { count: sales.data.sales_count }))}
            </Tile>
            <Tile
              label={t(`dashboard.grossProfit_${period}`)}
              icon={TrendingUpIcon}
              value={sales.data && formatTZS(sales.data.gross_profit)}
              loading={sales.isPending}
              error={sales.isError}
            >
              {sales.data && t('dashboard.grossProfitHint', { cogs: formatTZS(sales.data.cogs) })}
            </Tile>
            {canSeeExpenses && (
              <>
                <Tile
                  label={t(`dashboard.expenses_${period}`)}
                  icon={WalletIcon}
                  to="/expenses"
                  value={sales.data?.expenses == null ? undefined : formatTZS(sales.data.expenses)}
                  loading={sales.isPending}
                  error={sales.isError}
                >
                  {t('dashboard.expensesHint')}
                </Tile>
                <Tile
                  label={t(`dashboard.netProfit_${period}`)}
                  icon={CoinsIcon}
                  value={sales.data?.net_profit == null ? undefined : formatTZS(sales.data.net_profit)}
                  loading={sales.isPending}
                  error={sales.isError}
                >
                  {t('dashboard.netProfitHint')}
                </Tile>
              </>
            )}
            <Tile
              label={t(`dashboard.cash_${period}`)}
              icon={BanknoteIcon}
              value={sales.data && formatTZS(sales.data.cash_collected)}
              loading={sales.isPending}
              error={sales.isError}
            >
              {t('dashboard.cashHint')}
            </Tile>
            <Tile
              label={t('dashboard.owed')}
              icon={HandCoinsIcon}
              to="/customers?owes=true"
              value={sales.data && formatTZS(sales.data.outstanding_credit)}
              loading={sales.isPending}
              error={sales.isError}
            >
              {t('dashboard.owedHint')}
            </Tile>
          </>
        )}
        {canSeeStock && (
          <>
            <Tile
              label={t('dashboard.lowStock')}
              icon={AlertTriangleIcon}
              to="/inventory"
              value={summary.data?.low_stock}
              loading={summary.isPending}
              error={summary.isError}
            >
              {summary.data &&
                (summary.data.out_of_stock > 0
                  ? t('dashboard.outOfStockCount', { count: summary.data.out_of_stock })
                  : t('dashboard.lowStockHint'))}
            </Tile>
            <Tile
              label={t('dashboard.expiringSoon')}
              icon={CalendarClockIcon}
              to={`/inventory?view=${expiryView(summary.data?.expiry_warning_days ?? 30)}`}
              value={summary.data?.expiring_soon}
              loading={summary.isPending}
              error={summary.isError}
            >
              {summary.data &&
                (summary.data.expired > 0
                  ? t('dashboard.expiredBatches', { count: summary.data.expired })
                  : t('dashboard.expiringHint', { days: summary.data.expiry_warning_days }))}
            </Tile>
          </>
        )}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>{t('dashboard.liveTitle')}</CardTitle>
          <CardDescription>{t('dashboard.liveText')}</CardDescription>
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
  const { t } = useTranslation()
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
        {error ? t('common.couldNotLoad') : children}
      </CardContent>
    </Card>
  )
  return to ? <Link to={to}>{card}</Link> : card
}
