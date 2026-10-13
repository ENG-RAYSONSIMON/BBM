import { useQuery } from '@tanstack/react-query'
import { PlusIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'

import { DataList, PAGE_SIZE } from '@/components/data-list'
import type { Column } from '@/components/data-list'
import { FormField } from '@/components/form-field'
import { PageHeader } from '@/components/page-header'
import { PurchaseStatusBadge } from '@/components/purchase-status-badge'
import { RefSelect } from '@/components/ref-select'
import { SearchInput } from '@/components/search-input'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { useRefOptions } from '@/lib/catalog'
import { formatDate, formatTZS } from '@/lib/format'
import { PERMISSIONS } from '@/lib/types'
import type { Paginated, Purchase } from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'

const STATUSES = ['DRAFT', 'RECEIVED', 'CANCELLED'] as const

/** FR-14 purchases from suppliers. */
export function PurchasesPage() {
  const { can } = useAuth()
  const { t } = useTranslation()
  const STATUS_FILTERS = STATUSES.map((id) => ({ id, name: t(`purchases.status_${id}`) }))
  const navigate = useNavigate()
  const list = useListParams()
  const suppliers = useRefOptions('suppliers', can(PERMISSIONS.catalogView))
  const filters = {
    status: list.get('status'),
    supplier: list.get('supplier'),
    date_from: list.get('from'),
    date_to: list.get('to'),
  }
  // Purchase numbers ("P-000012" or "12") search by number; anything else by reference, supplier or note.
  const number = /^(p-?)?\d+$/i.test(list.search.trim()) ? list.search.trim() : ''
  const query = useQuery({
    queryKey: ['purchases', list.page, list.search, filters],
    queryFn: () =>
      api<Paginated<Purchase>>(
        `/purchases/${toQuery({
          page: list.page,
          page_size: PAGE_SIZE,
          ...(number ? { number } : { search: list.search }),
          ...filters,
        })}`,
      ),
    placeholderData: (previous) => previous,
  })

  const filtered = list.search || Object.values(filters).some(Boolean)
  const newButton = can(PERMISSIONS.purchasesManage) && (
    <Button asChild size="lg">
      <Link to="/purchases/new">
        <PlusIcon />
        {t('purchases.new')}
      </Link>
    </Button>
  )

  const columns: Column<Purchase>[] = [
    { header: t('purchases.number'), cell: (p) => <span className="font-medium">{p.purchase_number}</span> },
    { header: t('common.date'), cell: (p) => formatDate(p.purchase_date) },
    { header: t('common.supplier'), cell: (p) => p.supplier_name ?? '—' },
    { header: t('purchases.reference'), cell: (p) => p.reference || '—' },
    { header: t('common.items'), cell: (p) => p.item_count, className: 'text-right tabular-nums' },
    { header: t('common.total'), cell: (p) => formatTZS(p.total), className: 'text-right tabular-nums' },
    { header: t('common.status'), cell: (p) => <PurchaseStatusBadge status={p.status} />, className: 'text-right' },
  ]

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader
        title={t('purchases.title')}
        description={t('purchases.subtitle')}
        actions={newButton}
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SearchInput
          className="sm:col-span-2 lg:col-span-4"
          value={list.search}
          onChange={list.setSearch}
          placeholder={t('purchases.searchPlaceholder')}
        />
        <RefSelect hideLabel label={t('common.status')} noneLabel={t('purchases.anyStatus')} value={filters.status}
          onChange={(v) => list.set('status', v)} options={STATUS_FILTERS} />
        <RefSelect hideLabel label={t('common.supplier')} noneLabel={t('purchases.anySupplier')} value={filters.supplier}
          onChange={(v) => list.set('supplier', v)} options={suppliers.data} />
        <FormField label={t('common.from')} type="date" value={filters.date_from} onChange={(e) => list.set('from', e.target.value)} />
        <FormField label={t('common.to')} type="date" value={filters.date_to} onChange={(e) => list.set('to', e.target.value)} />
      </div>

      <DataList
        label={t('purchases.listLabel')}
        query={query}
        columns={columns}
        rowKey={(p) => p.id}
        onRowClick={(p) => navigate(`/purchases/${p.id}`)}
        page={list.page}
        onPageChange={list.setPage}
        empty={
          filtered
            ? { title: t('purchases.noMatch'), description: t('common.noMatchHint') }
            : {
                title: t('purchases.empty'),
                description: t('purchases.emptyText'),
                action: newButton,
              }
        }
        card={(p) => (
          <Link to={`/purchases/${p.id}`}>
            <Card className="gap-1 p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{p.purchase_number}</span>
                <span className="font-medium tabular-nums">{formatTZS(p.total)}</span>
              </div>
              <div className="text-muted-foreground flex items-center justify-between gap-2">
                <span className="truncate">
                  {formatDate(p.purchase_date)}
                  {p.supplier_name && ` · ${p.supplier_name}`}
                </span>
                <PurchaseStatusBadge status={p.status} />
              </div>
            </Card>
          </Link>
        )}
      />
    </div>
  )
}
