import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { DataList, PAGE_SIZE } from '@/components/data-list'
import type { Column } from '@/components/data-list'
import { FormField } from '@/components/form-field'
import { PageHeader } from '@/components/page-header'
import { RefSelect } from '@/components/ref-select'
import { SearchInput } from '@/components/search-input'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { AUDIT_ACTIONS } from '@/lib/types'
import type { AuditLogEntry, Paginated } from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'

/** FR-20: who did what, when. Owner only (audit.view). */
export function AuditPage() {
  const { t } = useTranslation()
  const list = useListParams()
  const filters = {
    action: list.get('action'),
    date_from: list.get('from'),
    date_to: list.get('to'),
  }
  const query = useQuery({
    queryKey: ['audit-logs', list.page, list.search, filters],
    queryFn: () =>
      api<Paginated<AuditLogEntry>>(
        `/audit-logs/${toQuery({ page: list.page, page_size: PAGE_SIZE, search: list.search, ...filters })}`,
      ),
    placeholderData: (previous) => previous,
  })

  const ACTION_FILTERS = AUDIT_ACTIONS.map((id) => ({ id, name: t(`audit.action_${id}`) }))
  const filtered = list.search || Object.values(filters).some(Boolean)

  const target = (entry: AuditLogEntry) => {
    const type = entry.target_type ? t(`audit.target_${entry.target_type}`, { defaultValue: entry.target_type }) : ''
    return [type, entry.target_label].filter(Boolean).join(': ') || '—'
  }
  const value = (v: unknown) => {
    if (v === null || v === undefined || v === '') return '—'
    if (typeof v === 'boolean') return v ? t('audit.yes') : t('audit.no')
    return String(v)
  }
  const details = (entry: AuditLogEntry) =>
    Object.entries(entry.changes).map(([field, change]) => {
      const label = t(`audit.field_${field}`, { defaultValue: field })
      if (Array.isArray(change) && change.length === 2) {
        return `${label}: ${value(change[0])} → ${value(change[1])}`
      }
      return change === true ? label : `${label}: ${value(change)}`
    })

  const columns: Column<AuditLogEntry>[] = [
    { header: t('common.when'), cell: (e) => <span className="whitespace-nowrap">{formatDateTime(e.created_at)}</span> },
    { header: t('audit.action'), cell: (e) => <Badge variant="outline">{t(`audit.action_${e.action}`)}</Badge> },
    { header: t('common.by'), cell: (e) => e.actor_name || t('audit.system') },
    { header: t('audit.target'), cell: target },
    {
      header: t('audit.details'),
      cell: (e) => (
        <ul className="text-muted-foreground grid gap-0.5 text-xs">
          {details(e).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ),
    },
  ]

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader title={t('audit.title')} description={t('audit.subtitle')} />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SearchInput
          className="sm:col-span-2 lg:col-span-4"
          value={list.search}
          onChange={list.setSearch}
          placeholder={t('audit.searchPlaceholder')}
        />
        <RefSelect hideLabel label={t('audit.action')} noneLabel={t('audit.anyAction')} value={filters.action}
          onChange={(v) => list.set('action', v)} options={ACTION_FILTERS} />
        <FormField label={t('common.from')} type="date" value={filters.date_from} onChange={(e) => list.set('from', e.target.value)} />
        <FormField label={t('common.to')} type="date" value={filters.date_to} onChange={(e) => list.set('to', e.target.value)} />
      </div>

      <DataList
        label={t('audit.listLabel')}
        query={query}
        columns={columns}
        rowKey={(e) => e.id}
        page={list.page}
        onPageChange={list.setPage}
        empty={
          filtered
            ? { title: t('audit.noMatch'), description: t('common.noMatchHint') }
            : { title: t('audit.empty'), description: t('audit.emptyText') }
        }
        card={(e) => (
          <Card className="gap-1 p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <Badge variant="outline">{t(`audit.action_${e.action}`)}</Badge>
              <span className="text-muted-foreground text-xs">{formatDateTime(e.created_at)}</span>
            </div>
            <p className="font-medium">{target(e)}</p>
            <p className="text-muted-foreground">{e.actor_name || t('audit.system')}</p>
            {details(e).map((line) => (
              <p key={line} className="text-muted-foreground text-xs">{line}</p>
            ))}
          </Card>
        )}
      />
    </div>
  )
}
