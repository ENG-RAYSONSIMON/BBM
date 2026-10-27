import { useQuery } from '@tanstack/react-query'
import { DownloadIcon } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { toast } from 'sonner'

import type { Column } from '@/components/data-list'
import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { PageHeader } from '@/components/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api, apiBlob } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { isoDate } from '@/lib/dates'
import { formatDate, formatMonth, formatTZS } from '@/lib/format'
import { PERMISSIONS, REPORT_PERIODS } from '@/lib/types'
import type {
  ExpensesReport,
  ExpiryReport,
  ProfitReport,
  ReportPeriod,
  SalesReport,
  StockValuationReport,
} from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'

const REPORTS = ['sales', 'profit', 'expenses', 'stock-valuation', 'expiry'] as const
type ReportKind = (typeof REPORTS)[number]

// i18n keys can't hold a hyphen comfortably: reports.kind_stockValuation.
const KEY = {
  sales: 'sales',
  profit: 'profit',
  expenses: 'expenses',
  'stock-valuation': 'stockValuation',
  expiry: 'expiry',
} as const satisfies Record<ReportKind, string>
const EXPIRY_WINDOWS = ['30', '60', '90'] as const
// All about buying cost or profit, so shown only with finance.view.
const FINANCE_REPORTS: readonly ReportKind[] = ['profit', 'stock-valuation', 'expiry']
// Show spending, so shown only with expenses.view.
const EXPENSE_REPORTS: readonly ReportKind[] = ['profit', 'expenses']

type AnyReport = SalesReport | ProfitReport | ExpensesReport | StockValuationReport | ExpiryReport

/** FR-18: sales, profit, expense, stock-value and expiry reports with CSV download. */
export function ReportsPage() {
  const { can } = useAuth()
  const { t } = useTranslation()
  const list = useListParams()
  const reports = REPORTS.filter(
    (r) =>
      (can(PERMISSIONS.financeView) || !FINANCE_REPORTS.includes(r)) &&
      (can(PERMISSIONS.expensesView) || !EXPENSE_REPORTS.includes(r)),
  )
  const kind = (reports as readonly string[]).includes(list.get('report')) ? (list.get('report') as ReportKind) : 'sales'
  const byPeriod = kind === 'sales' || kind === 'profit' || kind === 'expenses'
  const period = (REPORT_PERIODS as readonly string[]).includes(list.get('period'))
    ? (list.get('period') as ReportPeriod)
    : 'day'
  const within = (EXPIRY_WINDOWS as readonly string[]).includes(list.get('within')) ? list.get('within') : '60'

  const params = byPeriod
    ? { period, date_from: list.get('from'), date_to: list.get('to') }
    : kind === 'expiry'
      ? { within_days: within }
      : {}
  const query = useQuery({
    queryKey: ['reports', kind, params],
    queryFn: () => api<AnyReport>(`/reports/${kind}/${toQuery(params)}`),
    // Keep the old figures while filters change, but never show one report's data as another's.
    placeholderData: (previous, previousQuery) => (previousQuery?.queryKey[1] === kind ? previous : undefined),
  })

  const [downloading, setDownloading] = useState(false)
  async function download() {
    setDownloading(true)
    try {
      const blob = await apiBlob(`/reports/${kind}/export/${toQuery(params)}`)
      const href = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = href
      link.download = `bbm-${kind}-${isoDate(new Date())}.csv`
      link.click()
      URL.revokeObjectURL(href)
    } catch (error) {
      toast.error(error instanceof Error && error.message ? error.message : t('reports.couldNotDownload'))
    } finally {
      setDownloading(false)
    }
  }

  const downloadButton = can(PERMISSIONS.reportsExport) && (
    <Button size="lg" variant="outline" onClick={download} disabled={downloading || !query.data}>
      <DownloadIcon />
      {downloading ? t('common.working') : t('reports.downloadCsv')}
    </Button>
  )

  const data = query.data

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader title={t('reports.title')} description={t('reports.subtitle')} actions={downloadButton} />

      <div className="flex flex-wrap gap-2" role="group" aria-label={t('reports.choose')}>
        {reports.map((r) => (
          <Button
            key={r}
            size="sm"
            variant={kind === r ? 'default' : 'outline'}
            aria-pressed={kind === r}
            onClick={() => list.setMany({ report: r === 'sales' ? '' : r })}
          >
            {t(`reports.kind_${KEY[r]}`)}
          </Button>
        ))}
      </div>

      {byPeriod && (
        <div className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="grid gap-1.5 sm:col-span-2">
            <span className="text-sm font-medium">{t('reports.groupBy')}</span>
            <div className="flex flex-wrap gap-2" role="group" aria-label={t('reports.groupBy')}>
              {REPORT_PERIODS.map((p) => (
                <Button
                  key={p}
                  size="sm"
                  variant={period === p ? 'secondary' : 'ghost'}
                  aria-pressed={period === p}
                  onClick={() => list.set('period', p === 'day' ? '' : p)}
                >
                  {t(`reports.period_${p}`)}
                </Button>
              ))}
            </div>
          </div>
          <FormField label={t('common.from')} type="date" value={list.get('from')} onChange={(e) => list.set('from', e.target.value)} />
          <FormField label={t('common.to')} type="date" value={list.get('to')} onChange={(e) => list.set('to', e.target.value)} />
        </div>
      )}

      {kind === 'expiry' && (
        <div className="flex flex-wrap gap-2" role="group" aria-label={t('reports.window')}>
          {EXPIRY_WINDOWS.map((w) => (
            <Button
              key={w}
              size="sm"
              variant={within === w ? 'secondary' : 'ghost'}
              aria-pressed={within === w}
              onClick={() => list.set('within', w === '60' ? '' : w)}
            >
              {t('reports.withinDays', { days: w })}
            </Button>
          ))}
        </div>
      )}

      {query.isError ? (
        <div className="grid justify-items-start gap-3">
          <FormError message={query.error?.message ?? t('reports.couldNotLoad')} />
          <Button variant="outline" size="lg" onClick={() => query.refetch()}>
            {t('common.tryAgain')}
          </Button>
        </div>
      ) : !data ? (
        <div className="grid gap-3" role="status" aria-label={t('common.loadingLabel', { label: t(`reports.kind_${KEY[kind]}`) })}>
          <div className="grid gap-3 sm:grid-cols-3">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
          <Skeleton className="h-64" />
        </div>
      ) : kind === 'sales' ? (
        <SalesView report={data as SalesReport} />
      ) : kind === 'profit' ? (
        <ProfitView report={data as ProfitReport} />
      ) : kind === 'expenses' ? (
        <ExpensesView report={data as ExpensesReport} />
      ) : kind === 'stock-valuation' ? (
        <StockValuationView report={data as StockValuationReport} />
      ) : (
        <ExpiryView report={data as ExpiryReport} />
      )}
    </div>
  )
}

// ---- views per report ---------------------------------------------------------

function usePeriodLabel(period: ReportPeriod) {
  const { t } = useTranslation()
  return (start: string) =>
    period === 'week'
      ? t('reports.weekOf', { date: formatDate(start) })
      : period === 'month'
        ? formatMonth(start)
        : period === 'year'
          ? start.slice(0, 4)
          : formatDate(start)
}

function RangeNote({ from, to }: { from: string; to: string }) {
  const { t } = useTranslation()
  return <p className="text-muted-foreground text-sm">{t('reports.range', { from: formatDate(from), to: formatDate(to) })}</p>
}

function SalesView({ report }: { report: SalesReport }) {
  const { can } = useAuth()
  const { t } = useTranslation()
  const label = usePeriodLabel(report.period)
  const showProfit = can(PERMISSIONS.financeView)
  type Row = SalesReport['rows'][number]
  const profitColumns: Column<Row>[] = [
    { header: t('reports.col_cogs'), cell: (r) => formatTZS(r.cogs ?? '0'), className: 'text-right tabular-nums' },
    { header: t('reports.col_grossProfit'), cell: (r) => formatTZS(r.gross_profit ?? '0'), className: 'text-right tabular-nums' },
  ]
  const columns: Column<Row>[] = [
    { header: t('reports.col_period'), cell: (r) => label(r.period) },
    { header: t('reports.col_sales'), cell: (r) => r.sales_count, className: 'text-right tabular-nums' },
    { header: t('reports.col_revenue'), cell: (r) => formatTZS(r.revenue), className: 'text-right tabular-nums' },
    ...(showProfit ? profitColumns : []),
    { header: t('reports.col_cash'), cell: (r) => formatTZS(r.cash_collected), className: 'text-right tabular-nums' },
  ]
  const tiles: [string, string, string?][] = [
    [t('reports.col_revenue'), formatTZS(report.totals.revenue), t('reports.salesCount', { count: report.totals.sales_count })],
  ]
  if (showProfit) {
    tiles.push([
      t('reports.col_grossProfit'),
      formatTZS(report.totals.gross_profit ?? '0'),
      t('reports.costHint', { cogs: formatTZS(report.totals.cogs ?? '0') }),
    ])
  }
  tiles.push([t('reports.col_cash'), formatTZS(report.totals.cash_collected)])
  return (
    <>
      <RangeNote from={report.date_from} to={report.date_to} />
      <Tiles items={tiles} />
      <PeriodChart title={t('reports.col_revenue')} data={report.rows.map((r) => ({ label: label(r.period), value: Number(r.revenue) }))} />
      <ReportTable label={t('reports.kind_sales')} columns={columns} rows={report.rows} rowKey={(r) => r.period} />
    </>
  )
}

function ProfitView({ report }: { report: ProfitReport }) {
  const { t } = useTranslation()
  const label = usePeriodLabel(report.period)
  const columns: Column<ProfitReport['rows'][number]>[] = [
    { header: t('reports.col_period'), cell: (r) => label(r.period) },
    { header: t('reports.col_revenue'), cell: (r) => formatTZS(r.revenue), className: 'text-right tabular-nums' },
    { header: t('reports.col_grossProfit'), cell: (r) => formatTZS(r.gross_profit), className: 'text-right tabular-nums' },
    { header: t('reports.col_expenses'), cell: (r) => formatTZS(r.expenses), className: 'text-right tabular-nums' },
    { header: t('reports.col_netProfit'), cell: (r) => formatTZS(r.net_profit), className: 'text-right tabular-nums font-medium' },
  ]
  return (
    <>
      <RangeNote from={report.date_from} to={report.date_to} />
      <Tiles
        items={[
          [t('reports.col_grossProfit'), formatTZS(report.totals.gross_profit)],
          [t('reports.col_expenses'), formatTZS(report.totals.expenses)],
          [t('reports.col_netProfit'), formatTZS(report.totals.net_profit), t('reports.netHint')],
        ]}
      />
      <PeriodChart title={t('reports.col_netProfit')} data={report.rows.map((r) => ({ label: label(r.period), value: Number(r.net_profit) }))} />
      <ReportTable label={t('reports.kind_profit')} columns={columns} rows={report.rows} rowKey={(r) => r.period} />
    </>
  )
}

function ExpensesView({ report }: { report: ExpensesReport }) {
  const { t } = useTranslation()
  const label = usePeriodLabel(report.period)
  const perPeriod = new Map<string, number>()
  for (const row of report.rows) perPeriod.set(row.period, (perPeriod.get(row.period) ?? 0) + Number(row.total))
  const columns: Column<ExpensesReport['rows'][number]>[] = [
    { header: t('reports.col_period'), cell: (r) => label(r.period) },
    { header: t('common.category'), cell: (r) => r.category_name },
    { header: t('reports.col_count'), cell: (r) => r.count, className: 'text-right tabular-nums' },
    { header: t('common.total'), cell: (r) => formatTZS(r.total), className: 'text-right tabular-nums' },
  ]
  return (
    <>
      <RangeNote from={report.date_from} to={report.date_to} />
      <Tiles items={[[t('reports.col_expenses'), formatTZS(report.totals.total), t('reports.expenseCount', { count: report.totals.count })]]} />
      {report.rows.length > 0 && (
        <PeriodChart
          title={t('reports.col_expenses')}
          data={[...perPeriod].map(([period, value]) => ({ label: label(period), value }))}
        />
      )}
      <ReportTable
        label={t('reports.kind_expenses')}
        columns={columns}
        rows={report.rows}
        rowKey={(r) => `${r.period}-${r.category}`}
        empty={t('reports.noExpenses')}
      />
    </>
  )
}

function StockValuationView({ report }: { report: StockValuationReport }) {
  const { t } = useTranslation()
  const columns: Column<StockValuationReport['rows'][number]>[] = [
    { header: t('reports.col_product'), cell: (r) => <ProductName name={r.name} active={r.is_active} /> },
    { header: t('common.category'), cell: (r) => r.category_name || '—' },
    { header: t('reports.col_stock'), cell: (r) => `${r.stock_on_hand} ${r.unit}`, className: 'text-right tabular-nums' },
    { header: t('reports.col_costValue'), cell: (r) => formatTZS(r.cost_value), className: 'text-right tabular-nums' },
    { header: t('reports.col_retailValue'), cell: (r) => formatTZS(r.retail_value), className: 'text-right tabular-nums' },
  ]
  return (
    <>
      <p className="text-muted-foreground text-sm">{t('reports.asOf', { date: formatDate(report.as_of) })}</p>
      <Tiles
        items={[
          [t('reports.col_costValue'), formatTZS(report.totals.cost_value), t('reports.costValueHint')],
          [t('reports.col_retailValue'), formatTZS(report.totals.retail_value)],
          [t('reports.col_stock'), String(report.totals.stock_on_hand), t('reports.productCount', { count: report.totals.product_count })],
        ]}
      />
      <ReportTable
        label={t('reports.kind_stockValuation')}
        columns={columns}
        rows={report.rows}
        rowKey={(r) => r.product}
        empty={t('reports.noStock')}
      />
    </>
  )
}

function ExpiryView({ report }: { report: ExpiryReport }) {
  const { t } = useTranslation()
  const columns: Column<ExpiryReport['rows'][number]>[] = [
    { header: t('reports.col_product'), cell: (r) => <ProductName name={r.name} active={r.is_active} /> },
    { header: t('common.batch'), cell: (r) => r.batch_number },
    { header: t('common.expiry'), cell: (r) => formatDate(r.expiry_date) },
    {
      header: t('common.status'),
      cell: (r) =>
        r.status === 'expired' ? (
          <Badge variant="destructive">{t('reports.expiredDaysAgo', { count: -r.days_left })}</Badge>
        ) : (
          <Badge variant="outline">{t('reports.daysLeft', { count: r.days_left })}</Badge>
        ),
    },
    { header: t('reports.col_stock'), cell: (r) => r.stock_on_hand, className: 'text-right tabular-nums' },
    { header: t('reports.col_costValue'), cell: (r) => formatTZS(r.cost_value), className: 'text-right tabular-nums' },
  ]
  return (
    <>
      <p className="text-muted-foreground text-sm">{t('reports.asOf', { date: formatDate(report.as_of) })}</p>
      <Tiles
        items={[
          [t('reports.atRisk'), formatTZS(report.totals.cost_value), t('reports.batchCount', { count: report.totals.batch_count })],
          [t('reports.alreadyExpired'), formatTZS(report.totals.expired_value), t('reports.costValueHint')],
        ]}
      />
      <ReportTable
        label={t('reports.kind_expiry')}
        columns={columns}
        rows={report.rows}
        rowKey={(r) => r.batch}
        empty={t('reports.noExpiry', { days: report.within_days })}
      />
    </>
  )
}

// ---- building blocks ------------------------------------------------------------

function ProductName({ name, active }: { name: string; active: boolean }) {
  const { t } = useTranslation()
  return (
    <span className="flex flex-wrap items-center gap-2">
      {name}
      {!active && <Badge variant="outline">{t('reports.archived')}</Badge>}
    </span>
  )
}

function Tiles({ items }: { items: [label: string, value: string, hint?: string][] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {items.map(([label, value, hint]) => (
        <Card key={label} className="gap-1 p-4">
          <p className="text-muted-foreground text-sm">{label}</p>
          <p className="text-xl font-semibold tabular-nums">{value}</p>
          {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
        </Card>
      ))}
    </div>
  )
}

const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 })

/** One series per period: a single hue, no legend (the title names it). The table below is the text view. */
function PeriodChart({ title, data }: { title: string; data: { label: string; value: number }[] }) {
  return (
    <Card className="gap-2 p-4">
      <p className="text-sm font-medium">{title}</p>
      <figure aria-label={title} className="h-60 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={{ stroke: 'var(--border)' }}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
              minTickGap={16}
            />
            <YAxis
              width={48}
              tickLine={false}
              axisLine={false}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
              tickFormatter={(v: number) => compact.format(v)}
            />
            <Tooltip
              cursor={{ fill: 'var(--muted)' }}
              formatter={(value) => [formatTZS(Number(value)), title]}
              contentStyle={{
                background: 'var(--popover)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                color: 'var(--popover-foreground)',
                fontSize: 12,
              }}
              labelStyle={{ color: 'var(--popover-foreground)' }}
            />
            <Bar dataKey="value" fill="var(--report-series)" radius={[4, 4, 0, 0]} maxBarSize={40} />
          </BarChart>
        </ResponsiveContainer>
      </figure>
    </Card>
  )
}

/** All rows, unpaginated: a table from md up, cards below. */
function ReportTable<T>({
  label,
  columns,
  rows,
  rowKey,
  empty,
}: {
  label: string
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  empty?: string
}): ReactNode {
  if (rows.length === 0) {
    return <Card className="text-muted-foreground px-6 py-10 text-center text-sm">{empty}</Card>
  }
  const [first, ...rest] = columns
  return (
    <>
      <Card className="hidden overflow-hidden py-0 md:block">
        <Table aria-label={label}>
          <TableHeader>
            <TableRow>
              {columns.map((column) => (
                <TableHead key={column.header} className={column.className}>
                  {column.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={rowKey(row)}>
                {columns.map((column) => (
                  <TableCell key={column.header} className={column.className}>
                    {column.cell(row)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <ul className="grid gap-2 md:hidden" aria-label={label}>
        {rows.map((row) => (
          <li key={rowKey(row)}>
            <Card className="gap-1 p-3 text-sm">
              <div className="font-medium">{first.cell(row)}</div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                {rest.map((column) => (
                  <div key={column.header} className="contents">
                    <dt className="text-muted-foreground">{column.header}</dt>
                    <dd className="text-right tabular-nums">{column.cell(row)}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          </li>
        ))}
      </ul>
    </>
  )
}
