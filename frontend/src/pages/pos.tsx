import { useQuery, useQueryClient } from '@tanstack/react-query'
import { MinusIcon, PlusIcon, ShoppingCartIcon, Trash2Icon, UserIcon, XIcon } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { PageHeader } from '@/components/page-header'
import { ProductThumb } from '@/components/product-thumb'
import { SearchInput } from '@/components/search-input'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError, api } from '@/lib/api'
import { formatTZS } from '@/lib/format'
import { cartTotals, fromCents, tender, toCents } from '@/lib/money'
import type { Customer, Paginated, Product, SaleDetail } from '@/lib/types'
import { toQuery } from '@/lib/use-list-params'

type Line = { product: Product; quantity: number; discount: string }

type CustomerChoice =
  | { mode: 'none' }
  | { mode: 'existing'; customer: Customer }
  | { mode: 'new'; name: string; phone: string }

/** First message of a DRF error value: ["msg"] or {"field": ["msg"]}. */
function firstMessage(value: unknown): string | undefined {
  if (Array.isArray(value)) return typeof value[0] === 'string' ? value[0] : undefined
  if (value && typeof value === 'object') return firstMessage(Object.values(value)[0])
  return undefined
}

/** FR-11 point of sale: cart, discounts, cash received, change or credit. */
export function PosPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [lines, setLines] = useState<Line[]>([])
  const [received, setReceived] = useState('')
  const [customer, setCustomer] = useState<CustomerChoice>({ mode: 'none' })
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const products = useQuery({
    queryKey: ['products', 'pos', search],
    queryFn: () =>
      api<Paginated<Product>>(`/products/${toQuery({ search, is_active: 'true', page_size: 12, ordering: 'name' })}`),
    placeholderData: (previous) => previous,
  })

  const totals = cartTotals(lines.map((l) => ({ unitPrice: l.product.selling_price, quantity: l.quantity, discount: l.discount })))
  const receivedCents = toCents(received)
  const cash = tender(totals.total, receivedCents ?? 0)
  const hasCustomer =
    customer.mode === 'existing' || (customer.mode === 'new' && customer.name.trim() !== '')
  const needsCustomer = lines.length > 0 && cash.balance > 0 && !hasCustomer
  const blocked =
    lines.length === 0 ||
    receivedCents === null ||
    Object.keys(totals.lineErrors).length > 0 ||
    needsCustomer ||
    submitting

  function add(product: Product) {
    setError(null)
    setLines((current) => {
      const found = current.find((l) => l.product.id === product.id)
      if (found) {
        return current.map((l) =>
          l.product.id === product.id ? { ...l, quantity: Math.min(l.quantity + 1, product.stock_on_hand) } : l,
        )
      }
      return [...current, { product, quantity: 1, discount: '' }]
    })
  }

  function update(productId: string, change: Partial<Line>) {
    setLines((current) => current.map((l) => (l.product.id === productId ? { ...l, ...change } : l)))
  }

  function remove(productId: string) {
    setLines((current) => current.filter((l) => l.product.id !== productId))
  }

  async function submit() {
    if (blocked) return
    setSubmitting(true)
    setError(null)
    const body: Record<string, unknown> = {
      items: lines.map((l) => ({
        product: l.product.id,
        quantity: l.quantity,
        discount: fromCents(toCents(l.discount) ?? 0),
      })),
      amount_received: fromCents(receivedCents ?? 0),
      note: note.trim(),
    }
    if (customer.mode === 'existing') body.customer = customer.customer.id
    if (customer.mode === 'new' && customer.name.trim()) {
      body.new_customer = { name: customer.name.trim(), phone: customer.phone.trim() }
    }
    try {
      const sale = await api<SaleDetail>('/sales/', { method: 'POST', body })
      queryClient.setQueryData(['sale', sale.id], sale)
      await Promise.all(
        ['products', 'product', 'batches', 'movements', 'inventory', 'sales', 'customers'].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      )
      const change = toCents(sale.payments[0]?.change_given ?? '0') ?? 0
      toast.success(
        change > 0
          ? t('pos.savedChange', { receipt: sale.receipt_number, amount: formatTZS(fromCents(change)) })
          : t('pos.saved', { receipt: sale.receipt_number }),
      )
      navigate(`/sales/${sale.id}`)
    } catch (err) {
      if (err instanceof ApiError && err.data) {
        const data = err.data
        setError(
          firstMessage(data.items) ??
            firstMessage(data.customer) ??
            firstMessage(data.new_customer) ??
            firstMessage(data.amount_received) ??
            err.message,
        )
      } else {
        setError(err instanceof Error ? err.message : t('common.somethingWrong'))
      }
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader title={t('pos.title')} description={t('pos.subtitle')} />

      <div className="grid gap-4 lg:grid-cols-[1fr_26rem]">
        {/* Product picker */}
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
              {products.data.results.map((product) => {
                const inCart = lines.find((l) => l.product.id === product.id)?.quantity ?? 0
                const left = product.stock_on_hand - inCart
                return (
                  <li key={product.id}>
                    <button
                      type="button"
                      className="hover:bg-muted/60 bg-card flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                      onClick={() => add(product)}
                      disabled={left <= 0}
                      aria-label={t('common.addItem', { name: product.name })}
                    >
                      <ProductThumb product={product} className="size-10" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">{product.name}</p>
                        <p className="text-muted-foreground text-sm">
                          {formatTZS(product.selling_price)} ·{' '}
                          {product.stock_on_hand > 0
                            ? t('common.inStockCount', { count: product.stock_on_hand, unit: product.unit })
                            : t('common.outOfStock')}
                        </p>
                      </div>
                      <PlusIcon className="text-muted-foreground size-4 shrink-0" />
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        {/* Cart and payment */}
        <Card className="content-start lg:sticky lg:top-4 lg:self-start">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShoppingCartIcon className="size-5" />
              {t('pos.cart')}
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            {lines.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('common.tapToAdd')}</p>
            ) : (
              <ul className="divide-y" aria-label={t('pos.cartItems')}>
                {lines.map((line, index) => {
                  const gross = (toCents(line.product.selling_price) ?? 0) * line.quantity
                  const lineDiscount = toCents(line.discount) ?? 0
                  const max = line.product.stock_on_hand
                  return (
                    <li key={line.product.id} className="grid gap-2 py-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate font-medium">{line.product.name}</p>
                          <p className="text-muted-foreground text-sm">
                            {t('common.eachPrice', { price: formatTZS(line.product.selling_price) })}
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t('common.removeItem', { name: line.product.name })}
                          onClick={() => remove(line.product.id)}
                        >
                          <Trash2Icon />
                        </Button>
                      </div>
                      <div className="flex flex-wrap items-end gap-3">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="outline"
                            size="icon"
                            aria-label={t('pos.fewer', { name: line.product.name })}
                            disabled={line.quantity <= 1}
                            onClick={() => update(line.product.id, { quantity: line.quantity - 1 })}
                          >
                            <MinusIcon />
                          </Button>
                          <Input
                            aria-label={t('pos.quantityOf', { name: line.product.name })}
                            inputMode="numeric"
                            className="h-9 w-14 text-center tabular-nums"
                            value={line.quantity}
                            onChange={(event) => {
                              const value = Number(event.target.value.replace(/\D/g, ''))
                              update(line.product.id, { quantity: Math.max(1, Math.min(value || 1, max)) })
                            }}
                          />
                          <Button
                            variant="outline"
                            size="icon"
                            aria-label={t('pos.more', { name: line.product.name })}
                            disabled={line.quantity >= max}
                            onClick={() => update(line.product.id, { quantity: line.quantity + 1 })}
                          >
                            <PlusIcon />
                          </Button>
                        </div>
                        <div className="grid flex-1 gap-1">
                          <label className="text-muted-foreground text-xs" htmlFor={`discount-${line.product.id}`}>
                            {t('pos.discountTzs')}
                          </label>
                          <Input
                            id={`discount-${line.product.id}`}
                            inputMode="decimal"
                            placeholder="0"
                            className="h-9"
                            value={line.discount}
                            aria-invalid={totals.lineErrors[index] ? true : undefined}
                            onChange={(event) => update(line.product.id, { discount: event.target.value })}
                          />
                        </div>
                        <p className="ml-auto font-medium tabular-nums">
                          {formatTZS(fromCents(gross - Math.min(lineDiscount, gross)))}
                        </p>
                      </div>
                      {totals.lineErrors[index] && (
                        <p className="text-destructive text-sm">{t(totals.lineErrors[index] as never)}</p>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}

            <dl className="grid grid-cols-[1fr_auto] gap-y-1 border-t pt-3 text-sm">
              <dt className="text-muted-foreground">{t('common.subtotal')}</dt>
              <dd className="text-right tabular-nums">{formatTZS(fromCents(totals.subtotal))}</dd>
              {totals.discount > 0 && (
                <>
                  <dt className="text-muted-foreground">{t('common.discount')}</dt>
                  <dd className="text-right tabular-nums">−{formatTZS(fromCents(totals.discount))}</dd>
                </>
              )}
              <dt className="text-base font-semibold">{t('common.total')}</dt>
              <dd className="text-right text-base font-semibold tabular-nums" aria-label={t('common.total')}>
                {formatTZS(fromCents(totals.total))}
              </dd>
            </dl>

            <div className="grid gap-2">
              <FormField
                label={t('pos.cashReceived')}
                inputMode="decimal"
                placeholder="0"
                value={received}
                onChange={(event) => setReceived(event.target.value)}
                error={receivedCents === null ? t('errors.numberLike', { example: '20000' }) : undefined}
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={lines.length === 0}
                  onClick={() => setReceived(fromCents(totals.total))}
                >
                  {t('pos.exactCash')}
                </Button>
                <Button type="button" variant="outline" size="sm" disabled={lines.length === 0} onClick={() => setReceived('0')}>
                  {t('pos.allOnCredit')}
                </Button>
              </div>
              {lines.length > 0 && receivedCents !== null && (
                <p
                  className={cash.balance > 0 ? 'text-sm font-medium text-amber-700 dark:text-amber-400' : 'text-sm font-medium'}
                  aria-live="polite"
                >
                  {cash.balance > 0
                    ? t('pos.willBeOwed', { amount: formatTZS(fromCents(cash.balance)) })
                    : cash.change > 0
                      ? t('pos.changeToGive', { amount: formatTZS(fromCents(cash.change)) })
                      : t('pos.paidInFull')}
                </p>
              )}
            </div>

            <CustomerPicker value={customer} onChange={setCustomer} required={cash.balance > 0 && lines.length > 0} />

            <FormField label={t('common.noteOptional')} value={note} onChange={(event) => setNote(event.target.value)} maxLength={255} />

            <FormError message={error ?? undefined} />
            {needsCustomer && (
              <p className="text-destructive text-sm">{t('pos.needCustomer')}</p>
            )}
            <Button size="lg" onClick={submit} disabled={blocked}>
              {submitting ? t('common.saving') : t('pos.complete', { total: formatTZS(fromCents(totals.total)) })}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

/** Optional customer for a cash sale; required when something is owed. */
function CustomerPicker({
  value,
  onChange,
  required,
}: {
  value: CustomerChoice
  onChange: (value: CustomerChoice) => void
  required: boolean
}) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const customers = useQuery({
    queryKey: ['customers', 'pick', search],
    queryFn: () => api<Paginated<Customer>>(`/customers/${toQuery({ search, page_size: 5 })}`),
    enabled: value.mode === 'none' && search.trim() !== '',
  })

  if (value.mode === 'existing') {
    return (
      <div className="grid gap-1.5">
        <p className="text-sm font-medium">{t('pos.customer')}</p>
        <div className="flex items-center justify-between gap-2 rounded-md border p-2 text-sm">
          <span className="flex min-w-0 items-center gap-2">
            <UserIcon className="size-4 shrink-0" />
            <span className="truncate">
              {value.customer.name}
              {value.customer.phone && ` · ${value.customer.phone}`}
            </span>
          </span>
          <Button variant="ghost" size="icon" aria-label={t('pos.removeCustomer')} onClick={() => onChange({ mode: 'none' })}>
            <XIcon />
          </Button>
        </div>
        {(toCents(value.customer.balance) ?? 0) > 0 && (
          <p className="text-muted-foreground text-sm">
            {t('pos.alreadyOwes', { amount: formatTZS(value.customer.balance) })}
          </p>
        )}
      </div>
    )
  }

  if (value.mode === 'new') {
    return (
      <div className="grid gap-3 rounded-md border p-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">{t('pos.newCustomer')}</p>
          <Button variant="ghost" size="sm" onClick={() => onChange({ mode: 'none' })}>
            {t('common.cancel')}
          </Button>
        </div>
        <FormField
          label={t('common.name')}
          value={value.name}
          onChange={(event) => onChange({ ...value, name: event.target.value })}
          error={required && !value.name.trim() ? t('pos.enterCustomerName') : undefined}
        />
        <FormField
          label={t('common.phone')}
          inputMode="tel"
          value={value.phone}
          onChange={(event) => onChange({ ...value, phone: event.target.value })}
          hint={t('pos.phoneHint')}
        />
      </div>
    )
  }

  return (
    <div className="grid gap-2">
      <p className="text-sm font-medium">
        {t('pos.customer')}{' '}
        {required ? <span className="text-destructive">{t('pos.customerRequired')}</span> : t('pos.customerOptional')}
      </p>
      <SearchInput value={search} onChange={setSearch} placeholder={t('pos.findCustomer')} />
      {search.trim() !== '' && (
        <ul className="grid gap-1" aria-label={t('pos.matchingCustomers')}>
          {customers.data?.results.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className="hover:bg-muted w-full rounded-md px-2 py-1.5 text-left text-sm"
                onClick={() => onChange({ mode: 'existing', customer: c })}
              >
                {c.name}
                {c.phone && <span className="text-muted-foreground"> · {c.phone}</span>}
              </button>
            </li>
          ))}
          {customers.data?.count === 0 && <li className="text-muted-foreground px-2 text-sm">{t('pos.noMatch')}</li>}
        </ul>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="justify-self-start"
        onClick={() => onChange({ mode: 'new', name: search.trim(), phone: '' })}
      >
        <PlusIcon />
        {t('pos.newCustomer')}
      </Button>
    </div>
  )
}
