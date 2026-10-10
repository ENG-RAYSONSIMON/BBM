import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { PlusIcon } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { DataList, PAGE_SIZE } from '@/components/data-list'
import type { Column } from '@/components/data-list'
import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { PageHeader } from '@/components/page-header'
import { RefSelect } from '@/components/ref-select'
import { SearchInput } from '@/components/search-input'
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
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { formatTZS } from '@/lib/format'
import { applyServerErrors } from '@/lib/forms'
import { customerSchema } from '@/lib/schemas'
import type { CustomerValues } from '@/lib/schemas'
import { PERMISSIONS } from '@/lib/types'
import type { Customer, Paginated } from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'

const BALANCE_FILTERS = [
  { id: 'true', name: 'Owes money' },
  { id: 'false', name: 'Owes nothing' },
]

/** Customers and what each still owes on credit sales. */
export function CustomersPage() {
  const { can } = useAuth()
  const navigate = useNavigate()
  const list = useListParams()
  const [adding, setAdding] = useState(false)
  const hasBalance = list.get('owes')
  const query = useQuery({
    queryKey: ['customers', list.page, list.search, hasBalance],
    queryFn: () =>
      api<Paginated<Customer>>(
        `/customers/${toQuery({
          page: list.page,
          page_size: PAGE_SIZE,
          search: list.search,
          has_balance: hasBalance,
          // Debtors list: biggest balance first.
          ordering: hasBalance === 'true' ? '-balance' : 'name',
        })}`,
      ),
    placeholderData: (previous) => previous,
  })

  const addButton = can(PERMISSIONS.salesCreate) && (
    <Button size="lg" onClick={() => setAdding(true)}>
      <PlusIcon />
      Add customer
    </Button>
  )
  const salesOf = (c: Customer) => `/sales?customer=${c.id}`

  const columns: Column<Customer>[] = [
    { header: 'Name', cell: (c) => <span className="font-medium">{c.name}</span> },
    { header: 'Phone', cell: (c) => c.phone || '—' },
    { header: 'Bought', cell: (c) => formatTZS(c.total_bought), className: 'text-right tabular-nums' },
    { header: 'Paid', cell: (c) => formatTZS(c.amount_paid), className: 'text-right tabular-nums' },
    {
      header: 'Owes',
      cell: (c) =>
        Number(c.balance) > 0 ? <span className="font-medium">{formatTZS(c.balance)}</span> : '—',
      className: 'text-right tabular-nums',
    },
  ]

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader
        title="Customers"
        description="Who you sell to, and who still owes you money."
        actions={addButton}
      />

      <div className="grid gap-3 sm:grid-cols-[1fr_14rem]">
        <SearchInput value={list.search} onChange={list.setSearch} placeholder="Search name or phone" />
        <RefSelect hideLabel label="Balance" noneLabel="All customers" value={hasBalance}
          onChange={(v) => list.set('owes', v)} options={BALANCE_FILTERS} />
      </div>

      <DataList
        label="customers"
        query={query}
        columns={columns}
        rowKey={(c) => c.id}
        onRowClick={(c) => navigate(salesOf(c))}
        page={list.page}
        onPageChange={list.setPage}
        empty={
          list.search || hasBalance
            ? { title: hasBalance === 'true' ? 'Nobody owes you money' : 'No customers match' }
            : {
                title: 'No customers yet',
                description: 'Customers are added here or at the sale screen. A sale on credit needs one.',
                action: addButton,
              }
        }
        card={(c) => (
          <Link to={salesOf(c)}>
            <Card className="flex-row items-center justify-between gap-3 p-3 text-sm">
              <div className="min-w-0">
                <p className="truncate font-medium">{c.name}</p>
                <p className="text-muted-foreground">{c.phone || 'No phone'}</p>
              </div>
              <div className="text-right">
                {Number(c.balance) > 0 ? (
                  <p className="font-medium tabular-nums">Owes {formatTZS(c.balance)}</p>
                ) : (
                  <p className="text-muted-foreground">Owes nothing</p>
                )}
              </div>
            </Card>
          </Link>
        )}
      />

      <CustomerDialog open={adding} onOpenChange={setAdding} />
    </div>
  )
}

function CustomerDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const queryClient = useQueryClient()
  const empty: CustomerValues = { name: '', phone: '', notes: '' }
  const form = useForm<CustomerValues>({ resolver: zodResolver(customerSchema), defaultValues: empty })
  const { errors, isSubmitting } = form.formState

  function close(next: boolean) {
    if (!next) form.reset(empty)
    onOpenChange(next)
  }

  async function onSubmit(values: CustomerValues) {
    try {
      await api<Customer>('/customers/', { method: 'POST', body: values })
    } catch (error) {
      applyServerErrors(error, form.setError, ['name', 'phone', 'notes'])
      return
    }
    await queryClient.invalidateQueries({ queryKey: ['customers'] })
    toast.success('Customer added.')
    close(false)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add customer</DialogTitle>
          <DialogDescription>A phone number helps you follow up on what they owe.</DialogDescription>
        </DialogHeader>
        <form id="customer-form" className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <FormError message={errors.root?.server?.message} />
          <FormField label="Name" error={errors.name?.message} {...form.register('name')} />
          <FormField label="Phone" inputMode="tel" error={errors.phone?.message} {...form.register('phone')} />
          <FormField label="Notes" error={errors.notes?.message} {...form.register('notes')} />
        </form>
        <DialogFooter>
          <Button variant="outline" size="lg" onClick={() => close(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" form="customer-form" size="lg" disabled={isSubmitting}>
            {isSubmitting ? 'Saving…' : 'Add customer'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
