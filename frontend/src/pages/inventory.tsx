import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'

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

const VIEWS = [
  { id: 'low', label: 'Low stock' },
  { id: '7', label: 'Expiring ≤ 7 days' },
  { id: '30', label: '≤ 30 days' },
  { id: '60', label: '≤ 60 days' },
  { id: 'expired', label: 'Expired' },
] as const

/** FR-9: low-stock and expiry views, computed live by the API. */
export function InventoryPage() {
  const list = useListParams()
  const view = VIEWS.some((v) => v.id === list.get('view')) ? list.get('view') : 'low'

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader title="Inventory alerts" description="Products running low and batches near or past expiry." />
      <Tabs value={view} onValueChange={(next) => list.set('view', next === 'low' ? '' : next)}>
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
          <TabsList>
            {VIEWS.map((v) => (
              <TabsTrigger key={v.id} value={v.id}>
                {v.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
      </Tabs>
      <SearchInput value={list.search} onChange={list.setSearch} placeholder="Search products" />
      {view === 'low' ? <LowStockList /> : <ExpiryList view={view} />}
    </div>
  )
}

function LowStockList() {
  const list = useListParams()
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
      header: 'Product',
      cell: (p) => (
        <div className="flex items-center gap-3">
          <ProductThumb product={p} />
          <span className="font-medium">{p.name}</span>
        </div>
      ),
    },
    {
      header: 'In stock',
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
    { header: 'Alert at', cell: (p) => `${p.threshold} ${p.unit}`, className: 'text-right' },
    { header: 'Supplier', cell: (p) => p.supplier_detail?.name ?? '—' },
  ]

  return (
    <DataList
      label="low-stock products"
      query={query}
      columns={columns}
      rowKey={(p) => p.id}
      onRowClick={(p) => navigate(`/products/${p.id}`)}
      page={list.page}
      onPageChange={list.setPage}
      empty={{ title: 'Nothing is running low', description: 'Products at or below their alert level show up here.' }}
      card={(p) => (
        <Link to={`/products/${p.id}`}>
          <Card className="flex-row items-center gap-3 p-3">
            <ProductThumb product={p} className="size-12" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{p.name}</p>
              <p className="text-muted-foreground text-sm">
                Alert at {p.threshold} {p.unit}
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
    { header: 'Product', cell: (b) => <span className="font-medium">{b.product_name}</span> },
    { header: 'Batch', cell: (b) => b.batch_number },
    { header: 'Expiry', cell: (b) => formatDate(b.expiry_date) },
    { header: '', cell: (b) => <ExpiryBadge daysLeft={b.days_left} warnDays={366} /> },
    { header: 'Units left', cell: (b) => b.stock_on_hand, className: 'text-right tabular-nums' },
  ]

  return (
    <DataList
      label={expired ? 'expired batches' : 'expiring batches'}
      query={query}
      columns={columns}
      rowKey={(b) => b.id}
      onRowClick={(b) => navigate(`/products/${b.product}`)}
      page={list.page}
      onPageChange={list.setPage}
      empty={
        expired
          ? { title: 'No expired stock', description: 'Batches past their expiry date that still hold stock show up here.' }
          : { title: `Nothing expires in the next ${view} days` }
      }
      card={(b) => (
        <Link to={`/products/${b.product}`}>
          <Card className="gap-1 p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{b.product_name}</span>
              <ExpiryBadge daysLeft={b.days_left} warnDays={366} />
            </div>
            <p className="text-muted-foreground">
              Batch {b.batch_number} · {formatDate(b.expiry_date)} · {b.stock_on_hand} left
            </p>
          </Card>
        </Link>
      )}
    />
  )
}
