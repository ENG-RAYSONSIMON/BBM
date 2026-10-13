import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeftIcon, PackagePlusIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { PageHeader } from '@/components/page-header'
import { ProductThumb } from '@/components/product-thumb'
import { RefSelect } from '@/components/ref-select'
import { SearchInput } from '@/components/search-input'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError, api } from '@/lib/api'
import { useRefOptions } from '@/lib/catalog'
import { isoDate } from '@/lib/dates'
import { formatTZS } from '@/lib/format'
import { fromCents, toCents } from '@/lib/money'
import { lineAmount, lineError, purchaseTotal } from '@/lib/purchases'
import type { PurchaseLine } from '@/lib/purchases'
import type { Paginated, Product, PurchaseDetail } from '@/lib/types'
import { toQuery } from '@/lib/use-list-params'

type Header = { supplier: string; reference: string; purchaseDate: string; note: string }

/** First message of a DRF error value: ["msg"] or {"field": ["msg"]}. */
function firstMessage(value: unknown): string | undefined {
  if (Array.isArray(value)) return typeof value[0] === 'string' ? value[0] : firstMessage(value[0])
  if (value && typeof value === 'object') return firstMessage(Object.values(value)[0])
  return undefined
}

let nextKey = 0
const newKey = () => `line-${++nextKey}`

/** Create or edit a draft purchase (FR-14). */
export function PurchaseFormPage() {
  const { id } = useParams()
  const { t } = useTranslation()
  const existing = useQuery({
    queryKey: ['purchase', id],
    queryFn: () => api<PurchaseDetail>(`/purchases/${id}/`),
    enabled: Boolean(id),
  })

  if (id && existing.isPending) {
    return (
      <div className="mx-auto grid max-w-6xl gap-4" role="status" aria-label={t('purchases.loadingPurchase')}>
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (id && existing.isError) return <FormError message={existing.error.message} />
  if (existing.data && existing.data.status !== 'DRAFT') {
    return (
      <div className="mx-auto grid max-w-6xl justify-items-start gap-3">
        <FormError message={t('purchases.onlyDraftEdit')} />
        <Button variant="outline" size="lg" asChild>
          <Link to={`/purchases/${id}`}>{t('purchases.backToPurchase')}</Link>
        </Button>
      </div>
    )
  }
  return <PurchaseEditor key={id ?? 'new'} purchase={existing.data} />
}

function PurchaseEditor({ purchase }: { purchase?: PurchaseDetail }) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const suppliers = useRefOptions('suppliers')
  const [search, setSearch] = useState('')
  const [header, setHeader] = useState<Header>(() => ({
    supplier: purchase?.supplier ?? '',
    reference: purchase?.reference ?? '',
    purchaseDate: purchase?.purchase_date ?? isoDate(new Date()),
    note: purchase?.note ?? '',
  }))
  const [lines, setLines] = useState<PurchaseLine[]>(
    () =>
      purchase?.items.map((item) => ({
        key: newKey(),
        product: item.product,
        productName: item.product_name,
        tracksExpiry: item.tracks_expiry,
        quantity: String(item.quantity),
        unitCost: item.unit_cost,
        batchNumber: item.batch_number,
        expiryDate: item.expiry_date ?? '',
      })) ?? [],
  )
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState<'draft' | 'receive' | null>(null)

  const products = useQuery({
    queryKey: ['products', 'purchase', search],
    queryFn: () =>
      api<Paginated<Product>>(`/products/${toQuery({ search, is_active: 'true', page_size: 12, ordering: 'name' })}`),
    placeholderData: (previous) => previous,
  })

  const total = purchaseTotal(lines)
  const errors = lines.map(lineError)
  const blocked = lines.length === 0 || errors.some(Boolean) || submitting !== null

  function add(product: Product) {
    setError(null)
    setLines((current) => {
      // Products without expiry have one batch: add to the existing line.
      const found = !product.tracks_expiry && current.find((l) => l.product === product.id)
      if (found) {
        return current.map((l) =>
          l === found ? { ...l, quantity: String((Number(l.quantity) || 0) + 1) } : l,
        )
      }
      return [
        ...current,
        {
          key: newKey(),
          product: product.id,
          productName: product.name,
          tracksExpiry: product.tracks_expiry,
          quantity: '1',
          unitCost: product.cost_price,
          batchNumber: '',
          expiryDate: '',
        },
      ]
    })
  }

  function update(key: string, change: Partial<PurchaseLine>) {
    setLines((current) => current.map((l) => (l.key === key ? { ...l, ...change } : l)))
  }

  async function submit(receive: boolean) {
    if (blocked) return
    setSubmitting(receive ? 'receive' : 'draft')
    setError(null)
    const body = {
      supplier: header.supplier || null,
      reference: header.reference.trim(),
      purchase_date: header.purchaseDate || null,
      note: header.note.trim(),
      items: lines.map((l) => ({
        product: l.product,
        quantity: Number(l.quantity),
        unit_cost: fromCents(toCents(l.unitCost) ?? 0),
        batch_number: l.tracksExpiry ? l.batchNumber.trim() : '',
        expiry_date: l.tracksExpiry && l.expiryDate ? l.expiryDate : null,
      })),
    }
    try {
      let saved = await api<PurchaseDetail>(purchase ? `/purchases/${purchase.id}/` : '/purchases/', {
        method: purchase ? 'PUT' : 'POST',
        body,
      })
      if (receive) {
        try {
          saved = await api<PurchaseDetail>(`/purchases/${saved.id}/receive/`, { method: 'POST' })
        } catch (err) {
          // The draft is saved; show it with the reason it couldn't be received.
          queryClient.setQueryData(['purchase', saved.id], saved)
          await queryClient.invalidateQueries({ queryKey: ['purchases'] })
          toast.error(
            t('purchases.savedNotReceived', {
              number: saved.purchase_number,
              error: err instanceof Error ? err.message : '',
            }),
          )
          navigate(`/purchases/${saved.id}`)
          return
        }
      }
      queryClient.setQueryData(['purchase', saved.id], saved)
      const keys = receive
        ? ['purchases', 'products', 'product', 'batches', 'movements', 'inventory']
        : ['purchases']
      await Promise.all(keys.map((key) => queryClient.invalidateQueries({ queryKey: [key] })))
      toast.success(
        receive
          ? t('purchases.receivedToast', { number: saved.purchase_number })
          : t('purchases.savedDraft', { number: saved.purchase_number }),
      )
      navigate(`/purchases/${saved.id}`)
    } catch (err) {
      if (err instanceof ApiError && err.data) {
        const data = err.data
        setError(
          firstMessage(data.items) ??
            firstMessage(data.supplier) ??
            firstMessage(data.purchase_date) ??
            firstMessage(data.reference) ??
            err.message,
        )
      } else {
        setError(err instanceof Error ? err.message : t('common.somethingWrong'))
      }
      setSubmitting(null)
    }
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <Button variant="ghost" size="sm" className="justify-self-start" asChild>
        <Link to={purchase ? `/purchases/${purchase.id}` : '/purchases'}>
          <ArrowLeftIcon />
          {purchase ? purchase.purchase_number : t('purchases.title')}
        </Link>
      </Button>
      <PageHeader
        title={purchase ? t('purchases.editTitle', { number: purchase.purchase_number }) : t('purchases.new')}
        description={t('purchases.formText')}
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_30rem]">
        <section className="grid content-start gap-3" aria-label={t('pos.products')}>
          <SearchInput value={search} onChange={setSearch} placeholder={t('common.searchProducts')} />
          {products.isPending ? (
            <div className="grid gap-2 sm:grid-cols-2" role="status" aria-label={t('pos.loadingProducts')}>
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : products.isError ? (
            <FormError message={products.error.message} />
          ) : products.data.count === 0 ? (
            <p className="text-muted-foreground text-sm">
              {search ? t('common.noProductsMatch') : t('common.noActiveProducts')}
            </p>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {products.data.results.map((product) => (
                <li key={product.id}>
                  <button
                    type="button"
                    className="hover:bg-muted/60 bg-card flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors"
                    onClick={() => add(product)}
                    aria-label={t('common.addItem', { name: product.name })}
                  >
                    <ProductThumb product={product} className="size-10" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{product.name}</p>
                      <p className="text-muted-foreground text-sm">
                        {t('purchases.costInStock', {
                          cost: formatTZS(product.cost_price),
                          count: product.stock_on_hand,
                          unit: product.unit,
                        })}
                      </p>
                    </div>
                    <PlusIcon className="text-muted-foreground size-4 shrink-0" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <Card className="content-start lg:sticky lg:top-4 lg:self-start">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PackagePlusIcon className="size-5" />
              {t('purchases.purchase')}
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <RefSelect
                label={t('common.supplier')}
                noneLabel={t('purchases.noSupplier')}
                value={header.supplier}
                onChange={(supplier) => setHeader((h) => ({ ...h, supplier }))}
                options={suppliers.data}
              />
              <FormField
                label={t('purchases.invoiceRef')}
                value={header.reference}
                maxLength={64}
                onChange={(e) => setHeader((h) => ({ ...h, reference: e.target.value }))}
              />
              <FormField
                label={t('purchases.dateReceived')}
                type="date"
                value={header.purchaseDate}
                onChange={(e) => setHeader((h) => ({ ...h, purchaseDate: e.target.value }))}
              />
              <FormField
                label={t('common.noteOptional')}
                value={header.note}
                maxLength={255}
                onChange={(e) => setHeader((h) => ({ ...h, note: e.target.value }))}
              />
            </div>

            {lines.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('common.tapToAdd')}</p>
            ) : (
              <ul className="divide-y border-t" aria-label={t('purchases.lines')}>
                {lines.map((line, index) => {
                  const amount = lineAmount(line)
                  return (
                    <li key={line.key} className="grid gap-2 py-3">
                      <div className="flex items-start justify-between gap-2">
                        <p className="min-w-0 truncate font-medium">{line.productName}</p>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t('common.removeItem', { name: line.productName })}
                          onClick={() => setLines((current) => current.filter((l) => l.key !== line.key))}
                        >
                          <Trash2Icon />
                        </Button>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <LineInput label={t('common.quantity')} name={line.productName} inputMode="numeric" value={line.quantity}
                          onChange={(quantity) => update(line.key, { quantity })} />
                        <LineInput label={t('purchases.unitCost')} name={line.productName} inputMode="decimal" value={line.unitCost}
                          onChange={(unitCost) => update(line.key, { unitCost })} />
                        {line.tracksExpiry && (
                          <>
                            <LineInput label={t('purchases.batchNumber')} name={line.productName} value={line.batchNumber}
                              onChange={(batchNumber) => update(line.key, { batchNumber })} />
                            <LineInput label={t('purchases.expiryDate')} name={line.productName} type="date" value={line.expiryDate}
                              onChange={(expiryDate) => update(line.key, { expiryDate })} />
                          </>
                        )}
                      </div>
                      <div className="flex items-center justify-between gap-2 text-sm">
                        {errors[index] ? (
                          <p className="text-destructive">{t(errors[index] as never)}</p>
                        ) : line.tracksExpiry ? (
                          <p className="text-muted-foreground">{t('purchases.expiryForNewBatch')}</p>
                        ) : (
                          <span />
                        )}
                        <p className="font-medium tabular-nums">{formatTZS(fromCents(amount))}</p>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}

            <div className="flex items-center justify-between border-t pt-3 text-base font-semibold">
              <span>{t('common.total')}</span>
              <span className="tabular-nums" aria-label={t('common.total')}>
                {formatTZS(fromCents(total))}
              </span>
            </div>

            <FormError message={error ?? undefined} />
            <div className="grid gap-2 sm:grid-cols-2">
              <Button variant="outline" size="lg" onClick={() => submit(false)} disabled={blocked}>
                {submitting === 'draft' ? t('common.saving') : t('purchases.saveDraft')}
              </Button>
              <Button size="lg" onClick={() => submit(true)} disabled={blocked}>
                {submitting === 'receive' ? t('purchases.receiving') : t('purchases.saveReceive')}
              </Button>
            </div>
            <p className="text-muted-foreground text-xs">
              {t('purchases.receiveNote')}
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function LineInput({
  label,
  name,
  value,
  onChange,
  ...props
}: {
  label: string
  name: string
  value: string
  onChange: (value: string) => void
  inputMode?: 'numeric' | 'decimal'
  type?: string
}) {
  const { t } = useTranslation()
  return (
    <label className="grid gap-1">
      <span className="text-muted-foreground text-xs">{label}</span>
      <Input
        aria-label={t('purchases.fieldOf', { field: label, name })}
        className="h-9"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        {...props}
      />
    </label>
  )
}
