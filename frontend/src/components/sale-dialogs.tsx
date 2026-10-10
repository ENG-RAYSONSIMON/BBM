import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'

import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { api } from '@/lib/api'
import { formatTZS } from '@/lib/format'
import { applyServerErrors } from '@/lib/forms'
import { fromCents, tender, toCents } from '@/lib/money'
import { paymentSchema, voidSchema } from '@/lib/schemas'
import type { PaymentValues, VoidValues } from '@/lib/schemas'
import type { Sale, SaleDetail } from '@/lib/types'

/** Refresh everything a payment or void changes. */
async function invalidateSales(queryClient: ReturnType<typeof useQueryClient>, saleId: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['sale', saleId] }),
    queryClient.invalidateQueries({ queryKey: ['sales'] }),
    queryClient.invalidateQueries({ queryKey: ['customers'] }),
  ])
}

/** Cash paid towards what a credit sale still owes. */
export function RecordPaymentDialog({
  sale,
  open,
  onOpenChange,
}: {
  sale: Sale
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const empty: PaymentValues = { amount_received: '', note: '' }
  const form = useForm<PaymentValues>({ resolver: zodResolver(paymentSchema), defaultValues: empty })
  const { errors, isSubmitting } = form.formState
  const received = toCents(useWatch({ control: form.control, name: 'amount_received' }) ?? '')
  const balance = toCents(sale.balance) ?? 0
  const result = received === null || received === 0 ? null : tender(balance, received)

  function close(next: boolean) {
    if (!next) form.reset(empty)
    onOpenChange(next)
  }

  async function onSubmit(values: PaymentValues) {
    try {
      await api(`/sales/${sale.id}/payments/`, { method: 'POST', body: values })
    } catch (error) {
      applyServerErrors(error, form.setError, ['amount_received', 'note'])
      return
    }
    await invalidateSales(queryClient, sale.id)
    toast.success('Payment recorded.')
    close(false)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record payment</DialogTitle>
          <DialogDescription>
            {sale.receipt_number}
            {sale.customer_name ? ` · ${sale.customer_name}` : ''} · {formatTZS(sale.balance)} still owed
          </DialogDescription>
        </DialogHeader>
        <form id="record-payment" className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <FormError message={errors.root?.server?.message} />
          <div className="grid gap-2">
            <FormField
              label="Cash received"
              inputMode="decimal"
              autoFocus
              error={errors.amount_received?.message}
              {...form.register('amount_received')}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="justify-self-start"
              onClick={() => form.setValue('amount_received', fromCents(balance), { shouldValidate: true })}
            >
              Pay the full balance
            </Button>
          </div>
          {result && (
            <p className="text-sm" aria-live="polite">
              {result.change > 0
                ? `Give back ${formatTZS(fromCents(result.change))} change. The sale will be fully paid.`
                : result.balance > 0
                  ? `${formatTZS(fromCents(result.balance))} will still be owed.`
                  : 'The sale will be fully paid.'}
            </p>
          )}
          <FormField label="Note (optional)" error={errors.note?.message} {...form.register('note')} />
        </form>
        <DialogFooter>
          <Button variant="outline" size="lg" onClick={() => close(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" form="record-payment" size="lg" disabled={isSubmitting}>
            {isSubmitting ? 'Saving…' : 'Record payment'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Cancel a sale: stock goes back, cash collected is refunded. */
export function VoidSaleDialog({
  sale,
  open,
  onOpenChange,
}: {
  sale: Sale
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const form = useForm<VoidValues>({ resolver: zodResolver(voidSchema), defaultValues: { reason: '' } })
  const { errors, isSubmitting } = form.formState
  const paid = (toCents(sale.amount_paid) ?? 0) > 0

  function close(next: boolean) {
    if (!next) form.reset({ reason: '' })
    onOpenChange(next)
  }

  async function onSubmit(values: VoidValues) {
    let updated: SaleDetail
    try {
      updated = await api<SaleDetail>(`/sales/${sale.id}/void/`, { method: 'POST', body: values })
    } catch (error) {
      applyServerErrors(error, form.setError, ['reason'])
      return
    }
    queryClient.setQueryData(['sale', sale.id], updated)
    await Promise.all([
      invalidateSales(queryClient, sale.id),
      queryClient.invalidateQueries({ queryKey: ['products'] }),
      queryClient.invalidateQueries({ queryKey: ['product'] }),
      queryClient.invalidateQueries({ queryKey: ['batches'] }),
      queryClient.invalidateQueries({ queryKey: ['movements'] }),
      queryClient.invalidateQueries({ queryKey: ['inventory'] }),
    ])
    toast.success(`${sale.receipt_number} voided.`)
    close(false)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Void {sale.receipt_number}?</DialogTitle>
          <DialogDescription>
            The items go back into stock
            {paid ? ` and ${formatTZS(sale.amount_paid)} is recorded as refunded to the customer` : ''}. The
            sale stays on record as void. This can't be undone.
          </DialogDescription>
        </DialogHeader>
        <form id="void-sale" className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <FormError message={errors.root?.server?.message} />
          <FormField
            label="Reason"
            placeholder="e.g. Customer returned the items"
            error={errors.reason?.message}
            {...form.register('reason')}
          />
        </form>
        <DialogFooter>
          <Button variant="outline" size="lg" onClick={() => close(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" form="void-sale" variant="destructive" size="lg" disabled={isSubmitting}>
            {isSubmitting ? 'Voiding…' : 'Void sale'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
