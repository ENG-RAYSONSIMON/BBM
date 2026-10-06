import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'

import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { RefSelect } from '@/components/ref-select'
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
import { formatDate } from '@/lib/format'
import { applyServerErrors } from '@/lib/forms'
import { adjustmentSchema } from '@/lib/schemas'
import type { AdjustmentInput, AdjustmentValues } from '@/lib/schemas'
import type { Batch, MovementType, Product } from '@/lib/types'

type Kind = { id: string; name: string; type: MovementType; sign: 1 | -1 }

const ADJUSTMENT_KINDS: Kind[] = [
  { id: 'received', name: 'Stock received / opening stock', type: 'ADJUSTMENT', sign: 1 },
  { id: 'count_add', name: 'Count correction (add)', type: 'ADJUSTMENT', sign: 1 },
  { id: 'damage', name: 'Damaged', type: 'DAMAGE', sign: -1 },
  { id: 'expired', name: 'Expired', type: 'EXPIRY', sign: -1 },
  { id: 'count_remove', name: 'Count correction (remove)', type: 'ADJUSTMENT', sign: -1 },
]

const EMPTY: AdjustmentInput = {
  kind: 'received',
  batch: '',
  batch_number: '',
  expiry_date: '',
  quantity: '',
  reason: '',
}

/** FR-7 manual stock change for one product. Writes one ledger row. */
export function AdjustStockDialog({
  product,
  batches,
  open,
  onOpenChange,
}: {
  product: Product
  batches: Batch[]
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const form = useForm<AdjustmentInput, unknown, AdjustmentValues>({
    resolver: zodResolver(adjustmentSchema),
    defaultValues: EMPTY,
  })
  const { errors, isSubmitting } = form.formState
  const kindId = useWatch({ control: form.control, name: 'kind' })
  const batchId = useWatch({ control: form.control, name: 'batch' })
  const kind = ADJUSTMENT_KINDS.find((k) => k.id === kindId) ?? ADJUSTMENT_KINDS[0]
  const stockIn = kind.sign > 0
  // Products without expiry tracking use one automatic batch: no batch fields.
  const usesBatches = product.tracks_expiry
  const batchOptions = (stockIn ? batches : batches.filter((b) => b.stock_on_hand > 0)).map((b) => ({
    id: b.id,
    name: `${b.batch_number} · ${b.expiry_date ? `exp. ${formatDate(b.expiry_date)}` : 'no expiry'} · ${b.stock_on_hand} left`,
  }))

  function close(next: boolean) {
    if (!next) form.reset(EMPTY)
    onOpenChange(next)
  }

  async function onSubmit(values: AdjustmentValues) {
    if (usesBatches && !stockIn && !values.batch) {
      form.setError('batch', { message: 'Choose the batch to remove stock from.' })
      return
    }
    if (usesBatches && stockIn && !values.batch) {
      if (!values.batch_number) form.setError('batch_number', { message: 'Enter the batch or lot number.' })
      if (!values.expiry_date) form.setError('expiry_date', { message: 'Enter the expiry date.' })
      if (!values.batch_number || !values.expiry_date) return
    }

    const body: Record<string, unknown> = {
      product: product.id,
      movement_type: kind.type,
      quantity: kind.sign * values.quantity,
      reason: values.reason,
    }
    if (usesBatches && values.batch) body.batch = values.batch
    if (usesBatches && !values.batch) {
      body.batch_number = values.batch_number
      body.expiry_date = values.expiry_date
    }

    try {
      await api('/stock-movements/', { method: 'POST', body })
    } catch (error) {
      applyServerErrors(error, form.setError, ['quantity', 'batch', 'batch_number', 'expiry_date', 'reason'])
      return
    }
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['product', product.id] }),
      queryClient.invalidateQueries({ queryKey: ['batches', product.id] }),
      queryClient.invalidateQueries({ queryKey: ['movements'] }),
      queryClient.invalidateQueries({ queryKey: ['products'] }),
      queryClient.invalidateQueries({ queryKey: ['inventory'] }),
    ])
    toast.success(`Stock ${stockIn ? 'added' : 'removed'}.`)
    close(false)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90svh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Adjust stock</DialogTitle>
          <DialogDescription>
            {product.name} · {product.stock_on_hand} {product.unit} in stock
          </DialogDescription>
        </DialogHeader>

        <form id="adjust-stock" className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <FormError message={errors.root?.server?.message} />
          <Controller
            control={form.control}
            name="kind"
            render={({ field }) => (
              <RefSelect
                label="What happened?"
                value={field.value}
                onChange={(value) => {
                  field.onChange(value || 'received')
                  form.setValue('batch', '')
                }}
                options={ADJUSTMENT_KINDS}
                noneLabel="Choose…"
              />
            )}
          />

          {usesBatches && (
            <Controller
              control={form.control}
              name="batch"
              render={({ field }) => (
                <div className="grid gap-1.5">
                  <RefSelect
                    label="Batch"
                    value={field.value}
                    onChange={field.onChange}
                    options={batchOptions}
                    noneLabel={stockIn ? 'New batch' : 'Choose a batch'}
                  />
                  {errors.batch && <p className="text-destructive text-sm">{errors.batch.message}</p>}
                </div>
              )}
            />
          )}

          {usesBatches && stockIn && !batchId && (
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Batch / lot number" error={errors.batch_number?.message}
                {...form.register('batch_number')} />
              <FormField label="Expiry date" type="date" error={errors.expiry_date?.message}
                {...form.register('expiry_date')} />
            </div>
          )}

          <FormField
            label={stockIn ? 'Quantity to add' : 'Quantity to remove'}
            inputMode="numeric"
            hint={product.unit}
            error={errors.quantity?.message}
            {...form.register('quantity')}
          />
          <FormField
            label="Note"
            placeholder={stockIn ? 'e.g. Delivery from supplier' : 'e.g. Bottle broken on shelf'}
            error={errors.reason?.message}
            {...form.register('reason')}
          />
        </form>

        <DialogFooter>
          <Button variant="outline" size="lg" onClick={() => close(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" form="adjust-stock" size="lg" disabled={isSubmitting}>
            {isSubmitting ? 'Saving…' : stockIn ? 'Add stock' : 'Remove stock'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
