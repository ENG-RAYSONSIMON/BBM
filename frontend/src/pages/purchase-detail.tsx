import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeftIcon, BanIcon, PackageCheckIcon, PencilIcon } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '@/components/confirm-dialog'
import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { PurchaseStatusBadge } from '@/components/purchase-status-badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { formatDate, formatDateTime, formatTZS } from '@/lib/format'
import { applyServerErrors } from '@/lib/forms'
import { cancelPurchaseSchema } from '@/lib/schemas'
import type { CancelPurchaseValues } from '@/lib/schemas'
import { PERMISSIONS } from '@/lib/types'
import type { PurchaseDetail } from '@/lib/types'

/** One purchase: its lines, status, and the draft actions. */
export function PurchaseDetailPage() {
  const { id = '' } = useParams()
  const { can } = useAuth()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [dialog, setDialog] = useState<'receive' | 'cancel' | null>(null)
  const query = useQuery({ queryKey: ['purchase', id], queryFn: () => api<PurchaseDetail>(`/purchases/${id}/`) })

  if (query.isPending) {
    return (
      <div className="mx-auto grid max-w-4xl gap-4" role="status" aria-label={t('purchases.loadingPurchase')}>
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (query.isError) {
    return (
      <div className="mx-auto grid max-w-4xl justify-items-start gap-3">
        <FormError message={query.error.message} />
        <Button variant="outline" size="lg" asChild>
          <Link to="/purchases">{t('purchases.backToPurchases')}</Link>
        </Button>
      </div>
    )
  }

  const purchase = query.data
  const isDraft = purchase.status === 'DRAFT'
  const canManage = can(PERMISSIONS.purchasesManage)

  async function receive() {
    const updated = await api<PurchaseDetail>(`/purchases/${purchase.id}/receive/`, { method: 'POST' })
    queryClient.setQueryData(['purchase', purchase.id], updated)
    await Promise.all(
      ['purchases', 'products', 'product', 'batches', 'movements', 'inventory'].map((key) =>
        queryClient.invalidateQueries({ queryKey: [key] }),
      ),
    )
    toast.success(t('purchases.receivedToast', { number: purchase.purchase_number }))
  }

  return (
    <div className="mx-auto grid max-w-4xl gap-4">
      <Button variant="ghost" size="sm" className="justify-self-start" asChild>
        <Link to="/purchases">
          <ArrowLeftIcon />
          {t('purchases.title')}
        </Link>
      </Button>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{purchase.purchase_number}</h1>
            <PurchaseStatusBadge status={purchase.status} />
          </div>
          <p className="text-muted-foreground">
            {formatDate(purchase.purchase_date)}
            {purchase.supplier_name && ` · ${purchase.supplier_name}`}
            {purchase.reference && ` · ${t('purchases.refShort', { ref: purchase.reference })}`}
          </p>
          <p className="text-muted-foreground text-sm">{t('purchases.createdBy', { name: purchase.created_by_name })}</p>
        </div>
        {isDraft && canManage && (
          <div className="flex flex-wrap gap-2">
            <Button size="lg" onClick={() => setDialog('receive')}>
              <PackageCheckIcon />
              {t('purchases.receive')}
            </Button>
            <Button variant="outline" size="lg" asChild>
              <Link to={`/purchases/${purchase.id}/edit`}>
                <PencilIcon />
                {t('common.edit')}
              </Link>
            </Button>
            <Button variant="destructive" size="lg" onClick={() => setDialog('cancel')}>
              <BanIcon />
              {t('purchases.cancelPurchase')}
            </Button>
          </div>
        )}
      </div>

      {isDraft && (
        <Card className="p-4 text-sm">
          {t('purchases.draftNote')}
        </Card>
      )}
      {purchase.status === 'RECEIVED' && (
        <Card className="p-4 text-sm">
          {t('purchases.receivedNote', {
            date: purchase.received_at ? formatDateTime(purchase.received_at) : '',
            by: purchase.received_by_name ? t('purchases.byName', { name: purchase.received_by_name }) : '',
          })}
        </Card>
      )}
      {purchase.status === 'CANCELLED' && (
        <Card className="border-destructive/40 p-4 text-sm">
          {t('purchases.cancelledNote', {
            date: purchase.cancelled_at ? formatDateTime(purchase.cancelled_at) : '',
            by: purchase.cancelled_by_name ? t('purchases.byName', { name: purchase.cancelled_by_name }) : '',
            reason: purchase.cancel_reason,
          })}
        </Card>
      )}

      <Card className="py-0">
        <Table aria-label={t('purchases.lines')}>
          <TableHeader>
            <TableRow>
              <TableHead>{t('common.item')}</TableHead>
              <TableHead>{t('common.batch')}</TableHead>
              <TableHead className="text-right">{t('common.qty')}</TableHead>
              <TableHead className="text-right">{t('purchases.unitCostShort')}</TableHead>
              <TableHead className="text-right">{t('common.amount')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {purchase.items.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="whitespace-normal">
                  <Link className="font-medium underline-offset-4 hover:underline" to={`/products/${item.product}`}>
                    {item.product_name}
                  </Link>
                </TableCell>
                <TableCell>
                  {item.tracks_expiry ? (
                    <>
                      {item.batch_number}
                      {item.expiry_date && (
                        <span className="text-muted-foreground">
                          {t('purchases.expShort', { date: formatDate(item.expiry_date) })}
                        </span>
                      )}
                    </>
                  ) : (
                    '—'
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">{item.quantity}</TableCell>
                <TableCell className="text-right tabular-nums">{formatTZS(item.unit_cost)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatTZS(item.line_total)}</TableCell>
              </TableRow>
            ))}
            <TableRow>
              <TableCell colSpan={4} className="text-right font-semibold">
                {t('common.total')}
              </TableCell>
              <TableCell className="text-right font-semibold tabular-nums">{formatTZS(purchase.total)}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </Card>
      {purchase.note && <p className="text-muted-foreground text-sm">{t('sales.noteText', { note: purchase.note })}</p>}

      <ConfirmDialog
        open={dialog === 'receive'}
        onOpenChange={(open) => setDialog(open ? 'receive' : null)}
        title={t('purchases.receiveTitle', { number: purchase.purchase_number })}
        description={t('purchases.receiveText')}
        confirmLabel={t('purchases.receiveStock')}
        onConfirm={receive}
      />
      <CancelPurchaseDialog
        purchase={purchase}
        open={dialog === 'cancel'}
        onOpenChange={(open) => setDialog(open ? 'cancel' : null)}
      />
    </div>
  )
}

function CancelPurchaseDialog({
  purchase,
  open,
  onOpenChange,
}: {
  purchase: PurchaseDetail
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const form = useForm<CancelPurchaseValues>({
    resolver: zodResolver(cancelPurchaseSchema),
    defaultValues: { reason: '' },
  })
  const { errors, isSubmitting } = form.formState

  function close(next: boolean) {
    if (!next) form.reset({ reason: '' })
    onOpenChange(next)
  }

  async function onSubmit(values: CancelPurchaseValues) {
    let updated: PurchaseDetail
    try {
      updated = await api<PurchaseDetail>(`/purchases/${purchase.id}/cancel/`, { method: 'POST', body: values })
    } catch (error) {
      applyServerErrors(error, form.setError, ['reason'])
      return
    }
    queryClient.setQueryData(['purchase', purchase.id], updated)
    await queryClient.invalidateQueries({ queryKey: ['purchases'] })
    toast.success(t('purchases.cancelled', { number: purchase.purchase_number }))
    close(false)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('purchases.cancelTitle', { number: purchase.purchase_number })}</DialogTitle>
          <DialogDescription>{t('purchases.cancelText')}</DialogDescription>
        </DialogHeader>
        <form id="cancel-purchase" className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <FormError message={errors.root?.server?.message} />
          <FormField
            label={t('common.reason')}
            placeholder={t('purchases.cancelPlaceholder')}
            error={errors.reason?.message}
            {...form.register('reason')}
          />
        </form>
        <DialogFooter>
          <Button variant="outline" size="lg" onClick={() => close(false)} disabled={isSubmitting}>
            {t('purchases.keepIt')}
          </Button>
          <Button type="submit" form="cancel-purchase" variant="destructive" size="lg" disabled={isSubmitting}>
            {isSubmitting ? t('purchases.cancelling') : t('purchases.cancelPurchase')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
