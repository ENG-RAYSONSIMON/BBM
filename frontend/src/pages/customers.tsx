import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { PlusIcon } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

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

/** Customers and what each still owes on credit sales. */
export function CustomersPage() {
  const { can } = useAuth()
  const { t } = useTranslation()
  const BALANCE_FILTERS = [
    { id: 'true', name: t('customers.owesMoney') },
    { id: 'false', name: t('customers.owesNothing') },
  ]
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
      {t('customers.add')}
    </Button>
  )
  const salesOf = (c: Customer) => `/sales?customer=${c.id}`

  const columns: Column<Customer>[] = [
    { header: t('common.name'), cell: (c) => <span className="font-medium">{c.name}</span> },
    { header: t('common.phone'), cell: (c) => c.phone || '—' },
    { header: t('customers.bought'), cell: (c) => formatTZS(c.total_bought), className: 'text-right tabular-nums' },
    { header: t('customers.paid'), cell: (c) => formatTZS(c.amount_paid), className: 'text-right tabular-nums' },
    {
      header: t('customers.owes'),
      cell: (c) =>
        Number(c.balance) > 0 ? <span className="font-medium">{formatTZS(c.balance)}</span> : '—',
      className: 'text-right tabular-nums',
    },
  ]

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader
        title={t('customers.title')}
        description={t('customers.subtitle')}
        actions={addButton}
      />

      <div className="grid gap-3 sm:grid-cols-[1fr_14rem]">
        <SearchInput value={list.search} onChange={list.setSearch} placeholder={t('customers.searchPlaceholder')} />
        <RefSelect hideLabel label={t('customers.balance')} noneLabel={t('customers.allCustomers')} value={hasBalance}
          onChange={(v) => list.set('owes', v)} options={BALANCE_FILTERS} />
      </div>

      <DataList
        label={t('customers.listLabel')}
        query={query}
        columns={columns}
        rowKey={(c) => c.id}
        onRowClick={(c) => navigate(salesOf(c))}
        page={list.page}
        onPageChange={list.setPage}
        empty={
          list.search || hasBalance
            ? { title: hasBalance === 'true' ? t('customers.nobodyOwes') : t('customers.noMatch') }
            : {
                title: t('customers.empty'),
                description: t('customers.emptyText'),
                action: addButton,
              }
        }
        card={(c) => (
          <Link to={salesOf(c)}>
            <Card className="flex-row items-center justify-between gap-3 p-3 text-sm">
              <div className="min-w-0">
                <p className="truncate font-medium">{c.name}</p>
                <p className="text-muted-foreground">{c.phone || t('customers.noPhone')}</p>
              </div>
              <div className="text-right">
                {Number(c.balance) > 0 ? (
                  <p className="font-medium tabular-nums">{t('customers.owesAmount', { amount: formatTZS(c.balance) })}</p>
                ) : (
                  <p className="text-muted-foreground">{t('customers.owesNothing')}</p>
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
  const { t } = useTranslation()
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
    toast.success(t('customers.added'))
    close(false)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('customers.add')}</DialogTitle>
          <DialogDescription>{t('customers.addText')}</DialogDescription>
        </DialogHeader>
        <form id="customer-form" className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <FormError message={errors.root?.server?.message} />
          <FormField label={t('common.name')} error={errors.name?.message} {...form.register('name')} />
          <FormField label={t('common.phone')} inputMode="tel" error={errors.phone?.message} {...form.register('phone')} />
          <FormField label={t('customers.notes')} error={errors.notes?.message} {...form.register('notes')} />
        </form>
        <DialogFooter>
          <Button variant="outline" size="lg" onClick={() => close(false)} disabled={isSubmitting}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form="customer-form" size="lg" disabled={isSubmitting}>
            {isSubmitting ? t('common.saving') : t('customers.add')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
