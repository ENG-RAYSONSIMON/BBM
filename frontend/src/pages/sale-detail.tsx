import { useQuery } from '@tanstack/react-query'
import { ArrowLeftIcon, BanIcon, PlusIcon, WalletIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

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
  const [dialog, setDialog] = useState<'pay' | 'void' | null>(null)
  const query = useQuery({ queryKey: ['sale', id], queryFn: () => api<SaleDetail>(`/sales/${id}/`) })

  if (query.isPending) {
    return (
      <div className="mx-auto grid max-w-4xl gap-4" role="status" aria-label="Loading sale">
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
          <Link to="/sales">Back to sales</Link>
        </Button>
      </div>
    )
  }

  const sale = query.data
  const isVoid = sale.status === 'VOID'
  const owes = Number(sale.balance) > 0
  const refund = sale.payments.find((p) => p.kind === 'REFUND')
  const totals: [string, string, boolean?][] = [
    ['Subtotal', formatTZS(sale.subtotal)],
    ...(Number(sale.discount_total) > 0 ? ([['Discount', `−${formatTZS(sale.discount_total)}`]] as [string, string][]) : []),
    ['Total', formatTZS(sale.total), true],
    ['Paid', formatTZS(sale.amount_paid)],
    ...(isVoid ? [] : ([['Still owed', formatTZS(sale.balance), true]] as [string, string, boolean][])),
  ]

  return (
    <div className="mx-auto grid max-w-4xl gap-4">
      <Button variant="ghost" size="sm" className="justify-self-start" asChild>
        <Link to="/sales">
          <ArrowLeftIcon />
          Sales
        </Link>
      </Button>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{sale.receipt_number}</h1>
            <PaymentStatusBadge status={sale.payment_status} />
          </div>
          <p className="text-muted-foreground">
            {formatDateTime(sale.created_at)} · sold by {sale.sold_by_name}
          </p>
          {sale.customer && (
            <p className="mt-1">
              Customer:{' '}
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
              Record payment
            </Button>
          )}
          {can(PERMISSIONS.salesCreate) && (
            <Button variant="outline" size="lg" asChild>
              <Link to="/pos">
                <PlusIcon />
                New sale
              </Link>
            </Button>
          )}
          {!isVoid && can(PERMISSIONS.salesVoid) && (
            <Button variant="destructive" size="lg" onClick={() => setDialog('void')}>
              <BanIcon />
              Void
            </Button>
          )}
        </div>
      </div>

      {isVoid && (
        <Card className="border-destructive/40 p-4 text-sm">
          Voided {sale.voided_at && formatDateTime(sale.voided_at)}
          {sale.voided_by_name && ` by ${sale.voided_by_name}`}: {sale.void_reason}. The items went back into stock
          {refund && ` and ${formatTZS(refund.amount)} was refunded`}.
        </Card>
      )}

      <Card className="py-0">
        <Table aria-label="Items">
          <TableHeader>
            <TableRow>
              <TableHead>Item</TableHead>
              <TableHead className="text-right">Qty</TableHead>
              <TableHead className="text-right">Price</TableHead>
              <TableHead className="text-right">Discount</TableHead>
              <TableHead className="text-right">Amount</TableHead>
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
            <CardTitle>Totals</CardTitle>
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
                  <dt className="text-muted-foreground border-t pt-2">Cost of goods</dt>
                  <dd className="border-t pt-2 text-right tabular-nums">{formatTZS(sale.cost_total)}</dd>
                  <dt className="text-muted-foreground">Gross profit</dt>
                  <dd className="text-right tabular-nums">{formatTZS(sale.gross_profit)}</dd>
                </>
              )}
            </dl>
            {sale.note && <p className="text-muted-foreground mt-3 text-sm">Note: {sale.note}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Payments</CardTitle>
          </CardHeader>
          <CardContent>
            {sale.payments.length === 0 ? (
              <p className="text-muted-foreground text-sm">No cash received yet.</p>
            ) : (
              <ul className="divide-y text-sm" aria-label="Payments">
                {sale.payments.map((payment) => (
                  <li key={payment.id} className="grid gap-0.5 py-2">
                    <div className="flex justify-between gap-2">
                      <span className="font-medium">
                        {payment.kind === 'REFUND' ? 'Refund' : 'Cash payment'}
                      </span>
                      <span className={payment.kind === 'REFUND' ? 'text-destructive tabular-nums' : 'tabular-nums'}>
                        {payment.kind === 'REFUND' ? '−' : ''}
                        {formatTZS(payment.amount)}
                      </span>
                    </div>
                    <p className="text-muted-foreground">
                      {formatDateTime(payment.created_at)} · {payment.received_by_name}
                      {Number(payment.change_given) > 0 &&
                        ` · received ${formatTZS(payment.amount_received)}, change ${formatTZS(payment.change_given)}`}
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
