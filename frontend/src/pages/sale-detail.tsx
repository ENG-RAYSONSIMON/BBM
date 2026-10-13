import { useQuery } from '@tanstack/react-query'
import { ArrowLeftIcon, BanIcon, PlusIcon, WalletIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'

import { FormError } from '@/components/form-error'
import { PaymentStatusBadge } from '@/components/payment-status-badge'
import { RecordPaymentDialog, VoidSaleDialog } from '@/components/sale-dialogs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { formatDateTime, formatTZS } from '@/lib/format'
import { PERMISSIONS } from '@/lib/types'
import type { SaleDetail } from '@/lib/types'

/** Receipt view: items, payments, what is still owed, and actions. */
export function SaleDetailPage() {
  const { id = '' } = useParams()
  const { can } = useAuth()
  const { t } = useTranslation()
  const [dialog, setDialog] = useState<'pay' | 'void' | null>(null)
  const query = useQuery({ queryKey: ['sale', id], queryFn: () => api<SaleDetail>(`/sales/${id}/`) })

  if (query.isPending) {
    return (
      <div className="mx-auto grid max-w-4xl gap-4" role="status" aria-label={t('sales.loadingSale')}>
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
          <Link to="/sales">{t('sales.backToSales')}</Link>
        </Button>
      </div>
    )
  }

  const sale = query.data
  const isVoid = sale.status === 'VOID'
  const owes = Number(sale.balance) > 0
  const refund = sale.payments.find((p) => p.kind === 'REFUND')
  const totals: [string, string, boolean?][] = [
    [t('common.subtotal'), formatTZS(sale.subtotal)],
    ...(Number(sale.discount_total) > 0
      ? ([[t('common.discount'), `−${formatTZS(sale.discount_total)}`]] as [string, string][])
      : []),
    [t('common.total'), formatTZS(sale.total), true],
    [t('sales.paid'), formatTZS(sale.amount_paid)],
    ...(isVoid ? [] : ([[t('sales.stillOwed'), formatTZS(sale.balance), true]] as [string, string, boolean][])),
  ]

  return (
    <div className="mx-auto grid max-w-4xl gap-4">
      <Button variant="ghost" size="sm" className="justify-self-start" asChild>
        <Link to="/sales">
          <ArrowLeftIcon />
          {t('sales.title')}
        </Link>
      </Button>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{sale.receipt_number}</h1>
            <PaymentStatusBadge status={sale.payment_status} />
          </div>
          <p className="text-muted-foreground">
            {t('sales.soldBy', { date: formatDateTime(sale.created_at), name: sale.sold_by_name })}
          </p>
          {sale.customer && (
            <p className="mt-1">
              {t('sales.customerFilter')}{' '}
              <Link className="font-medium underline-offset-4 hover:underline" to={`/sales?customer=${sale.customer}`}>
                {sale.customer_name}
              </Link>
              {sale.customer_phone && <span className="text-muted-foreground"> · {sale.customer_phone}</span>}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {!isVoid && owes && can(PERMISSIONS.salesCreate) && (
            <Button size="lg" onClick={() => setDialog('pay')}>
              <WalletIcon />
              {t('sales.recordPayment')}
            </Button>
          )}
          {can(PERMISSIONS.salesCreate) && (
            <Button variant="outline" size="lg" asChild>
              <Link to="/pos">
                <PlusIcon />
                {t('sales.newSale')}
              </Link>
            </Button>
          )}
          {!isVoid && can(PERMISSIONS.salesVoid) && (
            <Button variant="destructive" size="lg" onClick={() => setDialog('void')}>
              <BanIcon />
              {t('sales.void')}
            </Button>
          )}
        </div>
      </div>

      {isVoid && (
        <Card className="border-destructive/40 p-4 text-sm">
          {t('sales.voidedText', {
            date: sale.voided_at ? formatDateTime(sale.voided_at) : '',
            by: sale.voided_by_name ? t('sales.voidedBy', { name: sale.voided_by_name }) : '',
            reason: sale.void_reason,
            refund: refund ? t('sales.voidedRefund', { amount: formatTZS(refund.amount) }) : '',
          })}
        </Card>
      )}

      <Card className="py-0">
        <Table aria-label={t('common.items')}>
          <TableHeader>
            <TableRow>
              <TableHead>{t('common.item')}</TableHead>
              <TableHead className="text-right">{t('common.qty')}</TableHead>
              <TableHead className="text-right">{t('common.price')}</TableHead>
              <TableHead className="text-right">{t('common.discount')}</TableHead>
              <TableHead className="text-right">{t('common.amount')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sale.items.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="whitespace-normal">
                  <Link className="font-medium underline-offset-4 hover:underline" to={`/products/${item.product}`}>
                    {item.product_name}
                  </Link>
                  <p className="text-muted-foreground text-xs">
                    {item.allocations.map((a) => `${a.batch_number} × ${a.quantity}`).join(', ')}
                  </p>
                </TableCell>
                <TableCell className="text-right tabular-nums">{item.quantity}</TableCell>
                <TableCell className="text-right tabular-nums">{formatTZS(item.unit_price)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {Number(item.discount) > 0 ? `−${formatTZS(item.discount)}` : '—'}
                </TableCell>
                <TableCell className="text-right tabular-nums">{formatTZS(item.line_total)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t('sales.totals')}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[1fr_auto] gap-y-1 text-sm">
              {totals.map(([label, value, strong]) => (
                <div key={label} className="contents">
                  <dt className={strong ? 'font-semibold' : 'text-muted-foreground'}>{label}</dt>
                  <dd className={strong ? 'text-right font-semibold tabular-nums' : 'text-right tabular-nums'}>{value}</dd>
                </div>
              ))}
              {!isVoid && (
                <>
                  <dt className="text-muted-foreground border-t pt-2">{t('sales.costOfGoods')}</dt>
                  <dd className="border-t pt-2 text-right tabular-nums">{formatTZS(sale.cost_total)}</dd>
                  <dt className="text-muted-foreground">{t('sales.grossProfit')}</dt>
                  <dd className="text-right tabular-nums">{formatTZS(sale.gross_profit)}</dd>
                </>
              )}
            </dl>
            {sale.note && <p className="text-muted-foreground mt-3 text-sm">{t('sales.noteText', { note: sale.note })}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('sales.payments')}</CardTitle>
          </CardHeader>
          <CardContent>
            {sale.payments.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('sales.noCashYet')}</p>
            ) : (
              <ul className="divide-y text-sm" aria-label={t('sales.payments')}>
                {sale.payments.map((payment) => (
                  <li key={payment.id} className="grid gap-0.5 py-2">
                    <div className="flex justify-between gap-2">
                      <span className="font-medium">
                        {payment.kind === 'REFUND' ? t('sales.refund') : t('sales.cashPayment')}
                      </span>
                      <span className={payment.kind === 'REFUND' ? 'text-destructive tabular-nums' : 'tabular-nums'}>
                        {payment.kind === 'REFUND' ? '−' : ''}
                        {formatTZS(payment.amount)}
                      </span>
                    </div>
                    <p className="text-muted-foreground">
                      {formatDateTime(payment.created_at)} · {payment.received_by_name}
                      {Number(payment.change_given) > 0 &&
                        t('sales.receivedChange', {
                          received: formatTZS(payment.amount_received),
                          change: formatTZS(payment.change_given),
                        })}
                    </p>
                    {payment.note && <p>{payment.note}</p>}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <RecordPaymentDialog sale={sale} open={dialog === 'pay'} onOpenChange={(open) => setDialog(open ? 'pay' : null)} />
      <VoidSaleDialog sale={sale} open={dialog === 'void'} onOpenChange={(open) => setDialog(open ? 'void' : null)} />
    </div>
  )
}
