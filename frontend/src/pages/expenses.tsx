import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileTextIcon, PaperclipIcon, PlusIcon, TagsIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '@/components/confirm-dialog'
import { DataList, PAGE_SIZE } from '@/components/data-list'
import type { Column } from '@/components/data-list'
import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { PageHeader } from '@/components/page-header'
import { RefSelect } from '@/components/ref-select'
import { SearchInput } from '@/components/search-input'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import i18n, { useTranslateMessage } from '@/i18n'
import { ApiError, api, apiBlob } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { isoDate } from '@/lib/dates'
import { formatDate, formatTZS } from '@/lib/format'
import { applyServerErrors } from '@/lib/forms'
import { expenseSchema } from '@/lib/schemas'
import type { ExpenseValues } from '@/lib/schemas'
import { PERMISSIONS } from '@/lib/types'
import type { Expense, ExpenseCategory, ExpensesSummary, Paginated } from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'

const RECEIPT_TYPES = 'image/jpeg,image/png,image/webp,application/pdf'

function useExpenseCategories() {
  return useQuery({
    queryKey: ['expense-categories', 'options'],
    queryFn: () => api<Paginated<ExpenseCategory>>('/expense-categories/?page_size=100&ordering=name'),
    select: (page) => page.results,
    staleTime: 60_000,
  })
}

/** Open a receipt in a new tab. It's fetched with the session token, never from a public URL. */
async function openReceipt(expenseId: string) {
  const tab = window.open('', '_blank')
  try {
    const blob = await apiBlob(`/expenses/${expenseId}/receipt/`)
    const url = URL.createObjectURL(blob)
    if (tab) tab.location.href = url
    else window.location.assign(url)
  } catch (error) {
    tab?.close()
    toast.error(error instanceof Error ? error.message : i18n.t('expenses.couldNotOpen'))
  }
}

/** FR-15 expenses, with the period total that feeds net profit. */
export function ExpensesPage() {
  const { can } = useAuth()
  const { t } = useTranslation()
  const list = useListParams()
  const categories = useExpenseCategories()
  const [editing, setEditing] = useState<Expense | 'new' | null>(null)
  const [managingCategories, setManagingCategories] = useState(false)
  const filters = { category: list.get('category'), date_from: list.get('from'), date_to: list.get('to') }

  const [now] = useState(() => new Date())
  const range = {
    date_from: filters.date_from || isoDate(new Date(now.getFullYear(), now.getMonth(), 1)),
    date_to: filters.date_to || isoDate(now),
  }
  const query = useQuery({
    queryKey: ['expenses', list.page, list.search, filters],
    queryFn: () =>
      api<Paginated<Expense>>(
        `/expenses/${toQuery({ page: list.page, page_size: PAGE_SIZE, search: list.search, ...filters })}`,
      ),
    placeholderData: (previous) => previous,
  })
  const summary = useQuery({
    queryKey: ['expenses', 'summary', range],
    queryFn: () => api<ExpensesSummary>(`/expenses/summary/${toQuery(range)}`),
  })

  const canManage = can(PERMISSIONS.expensesManage)
  const addButton = canManage && (
    <Button size="lg" onClick={() => setEditing('new')}>
      <PlusIcon />
      {t('expenses.add')}
    </Button>
  )
  const filtered = list.search || Object.values(filters).some(Boolean)

  const columns: Column<Expense>[] = [
    { header: t('common.date'), cell: (e) => formatDate(e.expense_date) },
    {
      header: t('expenses.whatFor'),
      cell: (e) => (
        <span className="flex items-center gap-1.5">
          <span className="font-medium">{e.description}</span>
          {e.has_receipt && <PaperclipIcon className="text-muted-foreground size-3.5" aria-label={t('expenses.hasReceipt')} />}
        </span>
      ),
    },
    { header: t('common.category'), cell: (e) => e.category_name },
    { header: t('expenses.paidTo'), cell: (e) => e.paid_to || '—' },
    { header: t('common.amount'), cell: (e) => formatTZS(e.amount), className: 'text-right tabular-nums' },
  ]

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader
        title={t('expenses.title')}
        description={t('expenses.subtitle')}
        actions={
          <>
            {canManage && (
              <Button variant="outline" size="lg" onClick={() => setManagingCategories(true)}>
                <TagsIcon />
                {t('expenses.categories')}
              </Button>
            )}
            {addButton}
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardDescription>
            {filters.date_from || filters.date_to
              ? `${formatDate(range.date_from)} – ${formatDate(range.date_to)}`
              : t('expenses.thisMonth')}
          </CardDescription>
          <CardTitle className="text-2xl tabular-nums" aria-label={t('expenses.periodTotal')}>
            {summary.isPending ? '…' : summary.isError ? '—' : formatTZS(summary.data.total)}
          </CardTitle>
        </CardHeader>
        {summary.data && summary.data.by_category.length > 0 && (
          <CardContent>
            <ul className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-sm" aria-label={t('expenses.byCategory')}>
              {summary.data.by_category.map((row) => (
                <li key={row.category}>
                  {row.category_name}: <span className="text-foreground tabular-nums">{formatTZS(row.total)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        )}
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SearchInput
          className="sm:col-span-2 lg:col-span-4"
          value={list.search}
          onChange={list.setSearch}
          placeholder={t('expenses.searchPlaceholder')}
        />
        <RefSelect hideLabel label={t('common.category')} noneLabel={t('expenses.allCategories')} value={filters.category}
          onChange={(v) => list.set('category', v)} options={categories.data} />
        <FormField label={t('common.from')} type="date" value={filters.date_from} onChange={(e) => list.set('from', e.target.value)} />
        <FormField label={t('common.to')} type="date" value={filters.date_to} onChange={(e) => list.set('to', e.target.value)} />
      </div>

      <DataList
        label={t('expenses.listLabel')}
        query={query}
        columns={columns}
        rowKey={(e) => e.id}
        onRowClick={(e) => setEditing(e)}
        page={list.page}
        onPageChange={list.setPage}
        empty={
          filtered
            ? { title: t('expenses.noMatch'), description: t('common.noMatchHint') }
            : { title: t('expenses.empty'), description: t('expenses.emptyText'), action: addButton }
        }
        card={(e) => (
          <button type="button" className="w-full text-left" onClick={() => setEditing(e)}>
            <Card className="gap-1 p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium">{e.description}</span>
                <span className="font-medium tabular-nums">{formatTZS(e.amount)}</span>
              </div>
              <p className="text-muted-foreground">
                {formatDate(e.expense_date)} · {e.category_name}
                {e.has_receipt && t('expenses.receiptTag')}
              </p>
            </Card>
          </button>
        )}
      />

      <ExpenseDialog
        // Remount per expense so the form and receipt state start fresh.
        key={editing === null ? 'closed' : editing === 'new' ? 'new' : editing.id}
        expense={editing === 'new' ? null : editing}
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
        categories={categories.data ?? []}
      />
      <CategoriesDialog open={managingCategories} onOpenChange={setManagingCategories} categories={categories.data ?? []} />
    </div>
  )
}

/** Add or edit an expense, with its receipt. Opens read-only without expenses.manage. */
function ExpenseDialog({
  expense,
  open,
  onOpenChange,
  categories,
}: {
  expense: Expense | null
  open: boolean
  onOpenChange: (open: boolean) => void
  categories: ExpenseCategory[]
}) {
  const { can } = useAuth()
  const { t } = useTranslation()
  const translate = useTranslateMessage()
  const queryClient = useQueryClient()
  const canManage = can(PERMISSIONS.expensesManage)
  const canDelete = can(PERMISSIONS.expensesDelete)
  const [values] = useState<ExpenseValues>(() =>
    expense
      ? {
          category: expense.category,
          amount: expense.amount,
          expense_date: expense.expense_date,
          description: expense.description,
          paid_to: expense.paid_to,
        }
      : { category: '', amount: '', expense_date: isoDate(new Date()), description: '', paid_to: '' },
  )
  const form = useForm<ExpenseValues>({ resolver: zodResolver(expenseSchema), defaultValues: values })
  const { errors, isSubmitting } = form.formState
  const [file, setFile] = useState<File | null>(null)
  const [hasReceipt, setHasReceipt] = useState(expense?.has_receipt ?? false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [receiptError, setReceiptError] = useState<string | null>(null)
  const close = onOpenChange

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ['expenses'] })
    await queryClient.invalidateQueries({ queryKey: ['sales', 'summary'] })
  }

  async function uploadReceipt(expenseId: string) {
    if (!file) return true
    const body = new FormData()
    body.append('receipt', file)
    try {
      await api(`/expenses/${expenseId}/receipt/`, { method: 'PUT', body })
      return true
    } catch (error) {
      const message =
        error instanceof ApiError ? (error.fieldErrors().receipt ?? error.message) : t('expenses.couldNotUpload')
      setReceiptError(message)
      return false
    }
  }

  async function onSubmit(data: ExpenseValues) {
    let saved: Expense
    try {
      saved = await api<Expense>(expense ? `/expenses/${expense.id}/` : '/expenses/', {
        method: expense ? 'PATCH' : 'POST',
        body: data,
      })
    } catch (error) {
      applyServerErrors(error, form.setError, ['category', 'amount', 'expense_date', 'description', 'paid_to'])
      return
    }
    const uploaded = await uploadReceipt(saved.id)
    await refresh()
    if (!uploaded) {
      toast.error(t('expenses.savedNoReceipt'))
      return
    }
    toast.success(expense ? t('expenses.updated') : t('expenses.recorded'))
    close(false)
  }

  async function removeReceipt() {
    if (!expense) return
    await api(`/expenses/${expense.id}/receipt/`, { method: 'DELETE' })
    setHasReceipt(false)
    await refresh()
  }

  async function deleteExpense() {
    if (!expense) return
    await api(`/expenses/${expense.id}/`, { method: 'DELETE' })
    await refresh()
    toast.success(t('expenses.deleted'))
    close(false)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{expense ? t('expenses.expense') : t('expenses.add')}</DialogTitle>
          <DialogDescription>
            {expense ? t('expenses.recordedBy', { name: expense.recorded_by_name }) : t('expenses.addText')}
          </DialogDescription>
        </DialogHeader>
        <form id="expense-form" className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <FormError message={errors.root?.server?.message} />
          <fieldset className="grid gap-4" disabled={!canManage}>
            <Controller
              control={form.control}
              name="category"
              render={({ field }) => (
                <div className="grid gap-1.5">
                  <RefSelect label={t('common.category')} noneLabel={t('expenses.chooseCategory')} value={field.value}
                    onChange={field.onChange} options={categories} disabled={!canManage} />
                  {errors.category && <p className="text-destructive text-sm">{translate(errors.category.message)}</p>}
                </div>
              )}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label={t('expenses.amountTzs')} inputMode="decimal" error={errors.amount?.message} {...form.register('amount')} />
              <FormField label={t('common.date')} type="date" error={errors.expense_date?.message} {...form.register('expense_date')} />
            </div>
            <FormField label={t('expenses.whatFor')} placeholder={t('expenses.whatForPlaceholder')} error={errors.description?.message}
              {...form.register('description')} />
            <FormField label={t('expenses.paidToOptional')} error={errors.paid_to?.message} {...form.register('paid_to')} />
          </fieldset>

          <div className="grid gap-1.5">
            <Label htmlFor="receipt-file">{t('expenses.receipt')}</Label>
            {hasReceipt && expense && (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Button type="button" variant="outline" size="sm" onClick={() => openReceipt(expense.id)}>
                  <FileTextIcon />
                  {t('expenses.viewReceipt')}
                </Button>
                {canManage && (
                  <Button type="button" variant="ghost" size="sm" onClick={() => removeReceipt().catch(() => setReceiptError(t('expenses.couldNotRemove')))}>
                    {t('common.remove')}
                  </Button>
                )}
              </div>
            )}
            {canManage && (
              <Input
                id="receipt-file"
                type="file"
                accept={RECEIPT_TYPES}
                onChange={(event) => {
                  setReceiptError(null)
                  setFile(event.target.files?.[0] ?? null)
                }}
              />
            )}
            {!hasReceipt && !canManage && <p className="text-muted-foreground text-sm">{t('expenses.noReceipt')}</p>}
            <p className={receiptError ? 'text-destructive text-sm' : 'text-muted-foreground text-sm'}>
              {receiptError ?? (canManage ? t('expenses.receiptHint') : '')}
            </p>
          </div>
        </form>
        <DialogFooter className="sm:justify-between">
          {expense && canDelete ? (
            <Button variant="ghost" size="lg" className="text-destructive" onClick={() => setConfirmDelete(true)}>
              <Trash2Icon />
              {t('common.delete')}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="outline" size="lg" onClick={() => close(false)} disabled={isSubmitting}>
              {canManage ? t('common.cancel') : t('common.close')}
            </Button>
            {canManage && (
              <Button type="submit" form="expense-form" size="lg" disabled={isSubmitting}>
                {isSubmitting ? t('common.saving') : expense ? t('common.save') : t('expenses.add')}
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t('expenses.deleteTitle')}
        description={t('expenses.deleteText')}
        confirmLabel={t('expenses.deleteExpense')}
        destructive
        onConfirm={deleteExpense}
      />
    </Dialog>
  )
}

/** Add categories; delete unused ones (expenses.delete). */
function CategoriesDialog({
  open,
  onOpenChange,
  categories,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  categories: ExpenseCategory[]
}) {
  const { can } = useAuth()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ['expense-categories'] })
  }

  async function add() {
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      await api('/expense-categories/', { method: 'POST', body: { name: name.trim(), description: '' } })
      setName('')
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? (err.fieldErrors().name ?? err.message) : t('expenses.couldNotAdd'))
    } finally {
      setSaving(false)
    }
  }

  async function remove(category: ExpenseCategory) {
    setError(null)
    try {
      await api(`/expense-categories/${category.id}/`, { method: 'DELETE' })
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('expenses.couldNotDelete'))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('expenses.categoriesTitle')}</DialogTitle>
          <DialogDescription>{t('expenses.categoriesText')}</DialogDescription>
        </DialogHeader>
        <FormError message={error ?? undefined} />
        <ul className="grid max-h-72 gap-1 overflow-y-auto" aria-label={t('expenses.categories')}>
          {categories.map((category) => (
            <li key={category.id} className="flex items-center justify-between gap-2 rounded-md px-2 py-1 text-sm">
              {category.name}
              {can(PERMISSIONS.expensesDelete) && (
                <Button variant="ghost" size="icon" aria-label={t('catalog.deleteItem', { name: category.name })} onClick={() => remove(category)}>
                  <Trash2Icon />
                </Button>
              )}
            </li>
          ))}
        </ul>
        <form
          className="flex items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            void add()
          }}
        >
          <div className="flex-1">
            <FormField label={t('expenses.newCategory')} value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
          </div>
          <Button type="submit" size="lg" disabled={saving || !name.trim()}>
            {t('common.add')}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
