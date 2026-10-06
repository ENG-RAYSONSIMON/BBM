import { useQuery } from '@tanstack/react-query'
import { PlusIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router'

import { DataList, PAGE_SIZE } from '@/components/data-list'
import type { Column } from '@/components/data-list'
import { PageHeader } from '@/components/page-header'
import { ProductThumb } from '@/components/product-thumb'
import { RefSelect } from '@/components/ref-select'
import { SearchInput } from '@/components/search-input'
import { StockBadge } from '@/components/stock-badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { useRefOptions } from '@/lib/catalog'
import { formatDate, formatTZS } from '@/lib/format'
import { PERMISSIONS } from '@/lib/types'
import type { Paginated, Product } from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'

const STOCK_FILTERS = [
  { id: 'low', name: 'Low stock' },
  { id: 'out', name: 'Out of stock' },
  { id: 'in', name: 'In stock' },
]
const STATUS_FILTERS = [
  { id: 'false', name: 'Archived' },
  { id: 'all', name: 'Active and archived' },
]

export function ProductsPage() {
  const { can } = useAuth()
  const navigate = useNavigate()
  const list = useListParams()
  const filters = {
    category: list.get('category'),
    brand: list.get('brand'),
    supplier: list.get('supplier'),
    stock_status: list.get('stock'),
    // Default view: active products only.
    is_active: list.get('status') === 'all' ? '' : list.get('status') || 'true',
  }
  const query = useQuery({
    queryKey: ['products', list.page, list.search, filters],
    queryFn: () =>
      api<Paginated<Product>>(
        `/products/${toQuery({ page: list.page, page_size: PAGE_SIZE, search: list.search, ...filters })}`,
      ),
    placeholderData: (previous) => previous,
  })
  const categories = useRefOptions('categories')
  const brands = useRefOptions('brands')
  const suppliers = useRefOptions('suppliers')

  const filtered = list.search || Object.entries(filters).some(([k, v]) => k !== 'is_active' && v)
  const canManage = can(PERMISSIONS.catalogManage)
  const addButton = canManage && (
    <Button asChild size="lg">
      <Link to="/products/new">
        <PlusIcon />
        Add product
      </Link>
    </Button>
  )

  const columns: Column<Product>[] = [
    {
      header: 'Product',
      cell: (p) => (
        <div className="flex items-center gap-3">
          <ProductThumb product={p} />
          <div className="min-w-0">
            <p className="truncate font-medium">{p.name}</p>
            <p className="text-muted-foreground truncate text-xs">
              {[p.sku, p.brand_detail?.name, p.category_detail?.name].filter(Boolean).join(' · ') || '—'}
            </p>
          </div>
          {!p.is_active && <span className="text-muted-foreground text-xs">(archived)</span>}
        </div>
      ),
    },
    { header: 'Price', cell: (p) => formatTZS(p.selling_price), className: 'text-right' },
    {
      header: 'Stock',
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
    { header: 'Nearest expiry', cell: (p) => formatDate(p.nearest_expiry), className: 'text-right' },
  ]

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader title="Products" description="Your catalog and current stock." actions={addButton} />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <SearchInput
          className="sm:col-span-2 lg:col-span-6"
          value={list.search}
          onChange={list.setSearch}
          placeholder="Search name, SKU or barcode"
        />
        <RefSelect hideLabel label="Category" noneLabel="All categories" value={filters.category}
          onChange={(v) => list.set('category', v)} options={categories.data} />
        <RefSelect hideLabel label="Brand" noneLabel="All brands" value={filters.brand}
          onChange={(v) => list.set('brand', v)} options={brands.data} />
        <RefSelect hideLabel label="Supplier" noneLabel="All suppliers" value={filters.supplier}
          onChange={(v) => list.set('supplier', v)} options={suppliers.data} />
        <RefSelect hideLabel label="Stock" noneLabel="Any stock level" value={filters.stock_status}
          onChange={(v) => list.set('stock', v)} options={STOCK_FILTERS} />
        <RefSelect hideLabel label="Status" noneLabel="Active" value={list.get('status')}
          onChange={(v) => list.set('status', v)} options={STATUS_FILTERS} />
      </div>

      <DataList
        label="products"
        query={query}
        columns={columns}
        rowKey={(p) => p.id}
        onRowClick={(p) => navigate(`/products/${p.id}`)}
        page={list.page}
        onPageChange={list.setPage}
        empty={
          filtered
            ? { title: 'No products match', description: 'Try a different search or clear the filters.' }
            : {
                title: 'No products yet',
                description: 'Add your first product, then record its stock.',
                action: addButton,
              }
        }
        card={(p) => (
          <Link to={`/products/${p.id}`}>
            <Card className="flex-row items-center gap-3 p-3">
              <ProductThumb product={p} className="size-12" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{p.name}</p>
                <p className="text-muted-foreground text-sm">{formatTZS(p.selling_price)}</p>
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
    </div>
  )
}
