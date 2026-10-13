import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'

import { DataList, PAGE_SIZE } from '@/components/data-list'
import type { Column } from '@/components/data-list'
import { PageHeader } from '@/components/page-header'
import { ProductThumb } from '@/components/product-thumb'
import { SearchInput } from '@/components/search-input'
import { ExpiryBadge, StockBadge } from '@/components/stock-badge'
import { Card } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/lib/api'
import { formatDate } from '@/lib/format'
import type { ExpiringBatch, Paginated, Product } from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'

// Labels are keys: inventory.view_<id>.
const VIEWS = ['low', '7', '30', '60', 'expired'] as const

/** FR-9: low-stock and expiry views, computed live by the API. */
export function InventoryPage() {
  const list = useListParams()
  const { t } = useTranslation()
  const view = (VIEWS as readonly string[]).includes(list.get('view')) ? list.get('view') : 'low'

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader title={t('inventory.title')} description={t('inventory.subtitle')} />
      <Tabs value={view} onValueChange={(next) => list.set('view', next === 'low' ? '' : next)}>
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
          <TabsList>
            {VIEWS.map((v) => (
              <TabsTrigger key={v} value={v}>
                {t(`inventory.view_${v}`)}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
      </Tabs>
      <SearchInput value={list.search} onChange={list.setSearch} placeholder={t('inventory.searchProducts')} />
      {view === 'low' ? <LowStockList /> : <ExpiryList view={view} />}
    </div>
  )
}

function LowStockList() {
  const list = useListParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const query = useQuery({
    queryKey: ['inventory', 'low-stock', list.page, list.search],
    queryFn: () =>
      api<Paginated<Product>>(
        `/inventory/low-stock/${toQuery({ page: list.page, page_size: PAGE_SIZE, search: list.search })}`,
      ),
    placeholderData: (previous) => previous,
  })

  const columns: Column<Product>[] = [
    {
      header: t('products.product'),
      cell: (p) => (
        <div className="flex items-center gap-3">
          <ProductThumb product={p} />
          <span className="font-medium">{p.name}</span>
        </div>
      ),
    },
    {
      header: t('inventory.inStock'),
      cell: (p) => (
        <div className="flex items-center justify-end gap-2">
          <StockBadge status={p.stock_status} />
          <span className="tabular-nums">
            {p.stock_on_hand} {p.unit}
          </span>
        </div>
      ),
      className: 'text-right',
    },
    { header: t('inventory.alertAt'), cell: (p) => `${p.threshold} ${p.unit}`, className: 'text-right' },
    { header: t('common.supplier'), cell: (p) => p.supplier_detail?.name ?? '—' },
  ]

  return (
    <DataList
      label={t('inventory.lowLabel')}
      query={query}
      columns={columns}
      rowKey={(p) => p.id}
      onRowClick={(p) => navigate(`/products/${p.id}`)}
      page={list.page}
      onPageChange={list.setPage}
      empty={{ title: t('inventory.lowEmpty'), description: t('inventory.lowEmptyText') }}
      card={(p) => (
        <Link to={`/products/${p.id}`}>
          <Card className="flex-row items-center gap-3 p-3">
            <ProductThumb product={p} className="size-12" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{p.name}</p>
              <p className="text-muted-foreground text-sm">
                {t('inventory.alertAtValue', { count: p.threshold, unit: p.unit })}
              </p>
            </div>
            <div className="grid justify-items-end gap-1 text-sm">
              <span className="tabular-nums">
                {p.stock_on_hand} {p.unit}
              </span>
              <StockBadge status={p.stock_status} />
            </div>
          </Card>
        </Link>
      )}
    />
  )
}

function ExpiryList({ view }: { view: string }) {
  const list = useListParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const expired = view === 'expired'
  const query = useQuery({
    queryKey: ['inventory', 'expiring', view, list.page, list.search],
    queryFn: () =>
      api<Paginated<ExpiringBatch>>(
        `/inventory/expiring/${toQuery({
          page: list.page,
          page_size: PAGE_SIZE,
          search: list.search,
          ...(expired ? { expired: 'true' } : { within: view }),
        })}`,
      ),
    placeholderData: (previous) => previous,
  })

  const columns: Column<ExpiringBatch>[] = [
    { header: t('products.product'), cell: (b) => <span className="font-medium">{b.product_name}</span> },
    { header: t('common.batch'), cell: (b) => b.batch_number },
    { header: t('common.expiry'), cell: (b) => formatDate(b.expiry_date) },
    { header: '', cell: (b) => <ExpiryBadge daysLeft={b.days_left} warnDays={366} /> },
    { header: t('inventory.unitsLeft'), cell: (b) => b.stock_on_hand, className: 'text-right tabular-nums' },
  ]

  return (
    <DataList
      label={expired ? t('inventory.expiredLabel') : t('inventory.expiringLabel')}
      query={query}
      columns={columns}
      rowKey={(b) => b.id}
      onRowClick={(b) => navigate(`/products/${b.product}`)}
      page={list.page}
      onPageChange={list.setPage}
      empty={
        expired
          ? { title: t('inventory.expiredEmpty'), description: t('inventory.expiredEmptyText') }
          : { title: t('inventory.expiringEmpty', { days: view }) }
      }
      card={(b) => (
        <Link to={`/products/${b.product}`}>
          <Card className="gap-1 p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{b.product_name}</span>
              <ExpiryBadge daysLeft={b.days_left} warnDays={366} />
            </div>
            <p className="text-muted-foreground">
              {t('inventory.batchCard', { batch: b.batch_number, date: formatDate(b.expiry_date), count: b.stock_on_hand })}
            </p>
          </Card>
        </Link>
      )}
    />
  )
}
