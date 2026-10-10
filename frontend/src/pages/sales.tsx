import { useQuery } from '@tanstack/react-query'
import { PlusIcon, XIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router'

import { DataList, PAGE_SIZE } from '@/components/data-list'
import type { Column } from '@/components/data-list'
import { FormField } from '@/components/form-field'
import { PageHeader } from '@/components/page-header'
import { PaymentStatusBadge } from '@/components/payment-status-badge'
import { RefSelect } from '@/components/ref-select'
import { SearchInput } from '@/components/search-input'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { formatDateTime, formatTZS } from '@/lib/format'
import { PERMISSIONS } from '@/lib/types'
import type { Customer, Paginated, Sale } from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'

const PAYMENT_STATUS_FILTERS = [
  { id: 'PAID', name: 'Paid' },
  { id: 'PARTIAL', name: 'Part paid' },
  { id: 'UNPAID', name: 'Unpaid' },
  { id: 'VOID', name: 'Void' },
]

export function SalesPage() {
  const { can } = useAuth()
  const navigate = useNavigate()
  const list = useListParams()
  const filters = {
    payment_status: list.get('payment'),
    date_from: list.get('from'),
    date_to: list.get('to'),
    customer: list.get('customer'),
  }
  // Receipt numbers ("S-000012" or "12") search by number; anything else by customer or note.
  const receipt = /^(s-?)?\d+$/i.test(list.search.trim()) ? list.search.trim() : ''
  const query = useQuery({
    queryKey: ['sales', list.page, list.search, filters],
    queryFn: () =>
      api<Paginated<Sale>>(
        `/sales/${toQuery({
          page: list.page,
          page_size: PAGE_SIZE,
          ...(receipt ? { receipt } : { search: list.search }),
          ...filters,
        })}`,
      ),
    placeholderData: (previous) => previous,
  })
  const customer = useQuery({
    queryKey: ['customers', 'detail', filters.customer],
    queryFn: () => api<Customer>(`/customers/${filters.customer}/`),
    enabled: Boolean(filters.customer),
  })

  const filtered = list.search || Object.values(filters).some(Boolean)
  const sellButton = can(PERMISSIONS.salesCreate) && (
    <Button asChild size="lg">
      <Link to="/pos">
        <PlusIcon />
        New sale
      </Link>
    </Button>
  )

  const columns: Column<Sale>[] = [
    { header: 'Receipt', cell: (s) => <span className="font-medium">{s.receipt_number}</span> },
    { header: 'When', cell: (s) => formatDateTime(s.created_at) },
    { header: 'Customer', cell: (s) => s.customer_name ?? '—' },
    { header: 'Total', cell: (s) => formatTZS(s.total), className: 'text-right tabular-nums' },
    {
      header: 'Owed',
      cell: (s) => (Number(s.balance) > 0 ? formatTZS(s.balance) : '—'),
      className: 'text-right tabular-nums',
    },
    { header: 'Status', cell: (s) => <PaymentStatusBadge status={s.payment_status} />, className: 'text-right' },
  ]

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader title="Sales" description="Every sale, what was paid and what is still owed." actions={sellButton} />

      {filters.customer && (
        <div className="flex items-center gap-2 text-sm">
          <span>
            Customer: <span className="font-medium">{customer.data?.name ?? '…'}</span>
            {customer.data && Number(customer.data.balance) > 0 && ` · owes ${formatTZS(customer.data.balance)}`}
          </span>
          <Button variant="ghost" size="sm" onClick={() => list.set('customer', '')}>
            <XIcon />
            Clear
          </Button>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SearchInput
          className="sm:col-span-2 lg:col-span-4"
          value={list.search}
          onChange={list.setSearch}
          placeholder="Search receipt number, customer name or phone"
        />
        <RefSelect hideLabel label="Payment" noneLabel="Any payment status" value={filters.payment_status}
          onChange={(v) => list.set('payment', v)} options={PAYMENT_STATUS_FILTERS} />
        <FormField label="From" type="date" value={filters.date_from} onChange={(e) => list.set('from', e.target.value)} />
        <FormField label="To" type="date" value={filters.date_to} onChange={(e) => list.set('to', e.target.value)} />
      </div>

      <DataList
        label="sales"
        query={query}
        columns={columns}
        rowKey={(s) => s.id}
        onRowClick={(s) => navigate(`/sales/${s.id}`)}
        page={list.page}
        onPageChange={list.setPage}
        empty={
          filtered
            ? { title: 'No sales match', description: 'Try a different search or clear the filters.' }
            : { title: 'No sales yet', description: 'Record your first sale from the sale screen.', action: sellButton }
        }
        card={(s) => (
          <Link to={`/sales/${s.id}`}>
            <Card className="gap-1 p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{s.receipt_number}</span>
                <span className="font-medium tabular-nums">{formatTZS(s.total)}</span>
              </div>
              <div className="text-muted-foreground flex items-center justify-between gap-2">
                <span className="truncate">
                  {formatDateTime(s.created_at)}
                  {s.customer_name && ` · ${s.customer_name}`}
                </span>
                <PaymentStatusBadge status={s.payment_status} />
              </div>
              {Number(s.balance) > 0 && <p>Owes {formatTZS(s.balance)}</p>}
            </Card>
          </Link>
        )}
      />
    </div>
  )
}
