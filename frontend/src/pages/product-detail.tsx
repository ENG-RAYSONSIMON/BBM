import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArchiveIcon, ArchiveRestoreIcon, ArrowLeftIcon, PencilIcon, ArrowUpDownIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { AdjustStockDialog } from '@/components/adjust-stock-dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { DataList, PAGE_SIZE } from '@/components/data-list'
import type { Column } from '@/components/data-list'
import { FormError } from '@/components/form-error'
import { ProductThumb } from '@/components/product-thumb'
import { ExpiryBadge, StockBadge } from '@/components/stock-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { formatDate, formatDateTime, formatQuantity, formatTZS } from '@/lib/format'
import { PERMISSIONS } from '@/lib/types'
import type { Batch, MovementType, Paginated, Product, StockMovement } from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'

const MOVEMENT_LABELS: Record<MovementType, string> = {
  PURCHASE: 'Purchase',
  SALE: 'Sale',
  ADJUSTMENT: 'Adjustment',
  DAMAGE: 'Damage',
  EXPIRY: 'Expired',
  TRANSFER: 'Transfer',
  RETURN: 'Returned (sale voided)',
}

function daysUntil(date: string) {
  const [y, m, d] = date.split('-').map(Number)
  const today = new Date()
  const start = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((Date.UTC(y, m - 1, d) - start) / 86_400_000)
}

export function ProductDetailPage() {
  const { id = '' } = useParams()
  const { can } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const list = useListParams()
  const [adjusting, setAdjusting] = useState(false)
  const [confirm, setConfirm] = useState<'archive' | 'delete' | null>(null)

  const productQuery = useQuery({ queryKey: ['product', id], queryFn: () => api<Product>(`/products/${id}/`) })
  const canSeeStock = can(PERMISSIONS.inventoryView)
  const batchesQuery = useQuery({
    queryKey: ['batches', id],
    queryFn: () => api<Paginated<Batch>>(`/products/${id}/batches/?page_size=100`),
    enabled: canSeeStock,
  })
  const movementsQuery = useQuery({
    queryKey: ['movements', id, list.page],
    queryFn: () =>
      api<Paginated<StockMovement>>(`/stock-movements/${toQuery({ product: id, page: list.page, page_size: PAGE_SIZE })}`),
    enabled: canSeeStock,
    placeholderData: (previous) => previous,
  })

  const setActive = useMutation({
    mutationFn: (is_active: boolean) =>
      api<Product>(`/products/${id}/`, { method: 'PATCH', body: { is_active } }),
    onSuccess: (product) => {
      queryClient.setQueryData(['product', id], product)
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      toast.success(product.is_active ? 'Product restored.' : 'Product archived.')
    },
  })

  if (productQuery.isPending) {
    return (
      <div className="mx-auto grid max-w-6xl gap-4" role="status" aria-label="Loading product">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-48" />
        <Skeleton className="h-48" />
      </div>
    )
  }
  if (productQuery.isError) {
    return (
      <div className="mx-auto grid max-w-6xl justify-items-start gap-3">
        <FormError message={productQuery.error.message} />
        <Button variant="outline" size="lg" asChild>
          <Link to="/products">Back to products</Link>
        </Button>
      </div>
    )
  }

  const product = productQuery.data
  const batches = batchesQuery.data?.results ?? []
  const facts: [string, string][] = [
    ['Selling price', formatTZS(product.selling_price)],
    ['Cost price', formatTZS(product.cost_price)],
    ['SKU', product.sku || '—'],
    ['Barcode', product.barcode || '—'],
    ['Category', product.category_detail?.name ?? '—'],
    ['Brand', product.brand_detail?.name ?? '—'],
    ['Supplier', product.supplier_detail?.name ?? '—'],
    [
      'Low-stock alert at',
      `${product.threshold} ${product.unit}${product.reorder_level === null ? ' (business default)' : ''}`,
    ],
  ]

  const movementColumns: Column<StockMovement>[] = [
    { header: 'When', cell: (m) => formatDateTime(m.created_at) },
    { header: 'Type', cell: (m) => MOVEMENT_LABELS[m.movement_type] },
    { header: 'Batch', cell: (m) => m.batch_number },
    {
      header: 'Qty',
      cell: (m) => (
        <span className={m.quantity < 0 ? 'text-destructive tabular-nums' : 'tabular-nums'}>
          {formatQuantity(m.quantity)}
        </span>
      ),
      className: 'text-right',
    },
    { header: 'Note', cell: (m) => m.reason || '—' },
    { header: 'By', cell: (m) => m.created_by_name },
  ]

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <Button variant="ghost" size="sm" className="justify-self-start" asChild>
        <Link to="/products">
          <ArrowLeftIcon />
          Products
        </Link>
      </Button>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-center gap-4">
          <ProductThumb product={product} className="size-16" />
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{product.name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="text-lg font-medium tabular-nums">
                {product.stock_on_hand} {product.unit}
              </span>
              <StockBadge status={product.stock_status} />
              {!product.is_active && <Badge variant="outline">Archived</Badge>}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {can(PERMISSIONS.inventoryAdjust) && product.is_active && (
            <Button size="lg" onClick={() => setAdjusting(true)}>
              <ArrowUpDownIcon />
              Adjust stock
            </Button>
          )}
          {can(PERMISSIONS.catalogManage) && (
            <>
              <Button variant="outline" size="lg" asChild>
                <Link to={`/products/${product.id}/edit`}>
                  <PencilIcon />
                  Edit
                </Link>
              </Button>
              {product.is_active ? (
                <Button variant="outline" size="lg" onClick={() => setConfirm('archive')}>
                  <ArchiveIcon />
                  Archive
                </Button>
              ) : (
                <Button variant="outline" size="lg" onClick={() => setActive.mutate(true)} disabled={setActive.isPending}>
                  <ArchiveRestoreIcon />
                  Restore
                </Button>
              )}
            </>
          )}
          {can(PERMISSIONS.catalogDelete) && (
            <Button variant="destructive" size="lg" onClick={() => setConfirm('delete')}>
              <Trash2Icon />
              Delete
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
              {facts.map(([label, value]) => (
                <div key={label} className="contents">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="break-words">{value}</dd>
                </div>
              ))}
            </dl>
            {product.description && <p className="text-muted-foreground mt-4 text-sm">{product.description}</p>}
          </CardContent>
        </Card>

        {canSeeStock && (
          <Card>
            <CardHeader>
              <CardTitle>Batches</CardTitle>
            </CardHeader>
            <CardContent>
              {batchesQuery.isPending ? (
                <Skeleton className="h-24" />
              ) : batchesQuery.isError ? (
                <FormError message={batchesQuery.error.message} />
              ) : batches.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  No stock recorded yet.
                  {can(PERMISSIONS.inventoryAdjust) && product.is_active && ' Use “Adjust stock” to add opening stock.'}
                </p>
              ) : (
                <ul className="divide-y">
                  {batches.map((batch) => (
                    <li key={batch.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                      <div className="min-w-0">
                        <p className="truncate font-medium">{batch.batch_number}</p>
                        <p className="text-muted-foreground">
                          {batch.expiry_date ? `Expires ${formatDate(batch.expiry_date)}` : 'No expiry'}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {batch.expiry_date && batch.stock_on_hand > 0 && (
                          <ExpiryBadge daysLeft={daysUntil(batch.expiry_date)} />
                        )}
                        <span className="tabular-nums">
                          {batch.stock_on_hand} {product.unit}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {canSeeStock && (
        <section className="grid gap-3" aria-labelledby="history-heading">
          <h2 id="history-heading" className="text-lg font-semibold">
            Stock history
          </h2>
          <DataList
            label="stock history"
            query={movementsQuery}
            columns={movementColumns}
            rowKey={(m) => m.id}
            page={list.page}
            onPageChange={list.setPage}
            empty={{ title: 'No stock movements yet' }}
            card={(m) => (
              <Card className="gap-1 p-3 text-sm">
                <div className="flex justify-between gap-2">
                  <span className="font-medium">{MOVEMENT_LABELS[m.movement_type]}</span>
                  <span className={m.quantity < 0 ? 'text-destructive tabular-nums' : 'tabular-nums'}>
                    {formatQuantity(m.quantity)}
                  </span>
                </div>
                <p className="text-muted-foreground">
                  {formatDateTime(m.created_at)} · {m.batch_number} · {m.created_by_name}
                </p>
                {m.reason && <p>{m.reason}</p>}
              </Card>
            )}
          />
        </section>
      )}

      <AdjustStockDialog product={product} batches={batches} open={adjusting} onOpenChange={setAdjusting} />
      <ConfirmDialog
        open={confirm === 'archive'}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Archive this product?"
        description="It disappears from lists and alerts but keeps its history. You can restore it later."
        confirmLabel="Archive"
        onConfirm={() => setActive.mutateAsync(false)}
      />
      <ConfirmDialog
        open={confirm === 'delete'}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Delete this product?"
        description="This can't be undone. Products with stock history can only be archived."
        confirmLabel="Delete"
        destructive
        onConfirm={async () => {
          await api(`/products/${product.id}/`, { method: 'DELETE' })
          await queryClient.invalidateQueries({ queryKey: ['products'] })
          toast.success('Product deleted.')
          navigate('/products', { replace: true })
        }}
      />
    </div>
  )
}
