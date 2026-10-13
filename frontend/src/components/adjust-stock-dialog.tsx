import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

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
import { useTranslateMessage } from '@/i18n'
import { api } from '@/lib/api'
import { formatDate } from '@/lib/format'
import { applyServerErrors } from '@/lib/forms'
import { adjustmentSchema } from '@/lib/schemas'
import type { AdjustmentInput, AdjustmentValues } from '@/lib/schemas'
import type { Batch, MovementType, Product } from '@/lib/types'

type Kind = {
  id: 'received' | 'count_add' | 'damage' | 'expired' | 'count_remove'
  type: MovementType
  sign: 1 | -1
}

// Labels are keys: adjust.kind_<id>.
const ADJUSTMENT_KINDS: Kind[] = [
  { id: 'received', type: 'ADJUSTMENT', sign: 1 },
  { id: 'count_add', type: 'ADJUSTMENT', sign: 1 },
  { id: 'damage', type: 'DAMAGE', sign: -1 },
  { id: 'expired', type: 'EXPIRY', sign: -1 },
  { id: 'count_remove', type: 'ADJUSTMENT', sign: -1 },
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
  const { t } = useTranslation()
  const translate = useTranslateMessage()
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
  const kindOptions = ADJUSTMENT_KINDS.map((k) => ({ id: k.id, name: t(`adjust.kind_${k.id}`) }))
  const batchOptions = (stockIn ? batches : batches.filter((b) => b.stock_on_hand > 0)).map((b) => ({
    id: b.id,
    name: t('adjust.batchOption', {
      batch: b.batch_number,
      expiry: b.expiry_date ? t('adjust.expiryShort', { date: formatDate(b.expiry_date) }) : t('adjust.noExpiry'),
      count: b.stock_on_hand,
    }),
  }))

  function close(next: boolean) {
    if (!next) form.reset(EMPTY)
    onOpenChange(next)
  }

  async function onSubmit(values: AdjustmentValues) {
    if (usesBatches && !stockIn && !values.batch) {
      form.setError('batch', { message: 'errors.chooseBatchToRemove' })
      return
    }
    if (usesBatches && stockIn && !values.batch) {
      if (!values.batch_number) form.setError('batch_number', { message: 'errors.enterBatchNumber' })
      if (!values.expiry_date) form.setError('expiry_date', { message: 'errors.enterExpiryDate' })
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
    toast.success(stockIn ? t('adjust.added') : t('adjust.removed'))
    close(false)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90svh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('adjust.title')}</DialogTitle>
          <DialogDescription>
            {t('adjust.subtitle', { name: product.name, count: product.stock_on_hand, unit: product.unit })}
          </DialogDescription>
        </DialogHeader>

        <form id="adjust-stock" className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <FormError message={errors.root?.server?.message} />
          <Controller
            control={form.control}
            name="kind"
            render={({ field }) => (
              <RefSelect
                label={t('adjust.whatHappened')}
                value={field.value}
                onChange={(value) => {
                  field.onChange(value || 'received')
                  form.setValue('batch', '')
                }}
                options={kindOptions}
                noneLabel={t('common.choose')}
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
                    label={t('common.batch')}
                    value={field.value}
                    onChange={field.onChange}
                    options={batchOptions}
                    noneLabel={stockIn ? t('adjust.newBatch') : t('adjust.chooseBatch')}
                  />
                  {errors.batch && <p className="text-destructive text-sm">{translate(errors.batch.message)}</p>}
                </div>
              )}
            />
          )}

          {usesBatches && stockIn && !batchId && (
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label={t('adjust.batchLot')} error={errors.batch_number?.message}
                {...form.register('batch_number')} />
              <FormField label={t('adjust.expiryDate')} type="date" error={errors.expiry_date?.message}
                {...form.register('expiry_date')} />
            </div>
          )}

          <FormField
            label={stockIn ? t('adjust.qtyAdd') : t('adjust.qtyRemove')}
            inputMode="numeric"
            hint={product.unit}
            error={errors.quantity?.message}
            {...form.register('quantity')}
          />
          <FormField
            label={t('common.note')}
            placeholder={stockIn ? t('adjust.notePlaceholderIn') : t('adjust.notePlaceholderOut')}
            error={errors.reason?.message}
            {...form.register('reason')}
          />
        </form>

        <DialogFooter>
          <Button variant="outline" size="lg" onClick={() => close(false)} disabled={isSubmitting}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form="adjust-stock" size="lg" disabled={isSubmitting}>
            {isSubmitting ? t('common.saving') : stockIn ? t('adjust.addStock') : t('adjust.removeStock')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
