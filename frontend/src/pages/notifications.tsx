import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangleIcon, CalendarClockIcon, CheckCheckIcon, PackageIcon } from 'lucide-react'
import type { ComponentType } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { DataList, PAGE_SIZE } from '@/components/data-list'
import type { Column } from '@/components/data-list'
import { PageHeader } from '@/components/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { api } from '@/lib/api'
import { formatDate, formatDateTime } from '@/lib/format'
import type { AppNotification, NotificationKind, Paginated } from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'
import { cn } from '@/lib/utils'

const ICONS: Record<NotificationKind, ComponentType<{ className?: string }>> = {
  LOW_STOCK: PackageIcon,
  EXPIRING: CalendarClockIcon,
  EXPIRED: AlertTriangleIcon,
}

/** The message for a notification, in the reader's language. */
function useNotificationText() {
  const { t } = useTranslation()
  return (n: AppNotification) => {
    const p = n.params
    const values = {
      name: p.name ?? '',
      stock: p.stock ?? 0,
      unit: p.unit ?? '',
      batch: p.batch_number ?? '',
      date: formatDate(p.expiry_date),
      count: p.days ?? 0,
    }
    switch (n.kind) {
      case 'LOW_STOCK':
        return t('notifications.text_LOW_STOCK', values)
      case 'EXPIRING':
        return t('notifications.text_EXPIRING', values)
      case 'EXPIRED':
        return t('notifications.text_EXPIRED', values)
    }
  }
}

/** FR-19 notification centre: low-stock and expiry alerts, newest first. */
export function NotificationsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const list = useListParams()
  const text = useNotificationText()
  const onlyUnread = list.get('show') === 'unread'
  const query = useQuery({
    queryKey: ['notifications', list.page, onlyUnread],
    queryFn: () =>
      api<Paginated<AppNotification>>(
        `/notifications/${toQuery({ page: list.page, page_size: PAGE_SIZE, unread: onlyUnread ? 'true' : '' })}`,
      ),
    placeholderData: (previous) => previous,
  })

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['notifications'] })
  const readOne = useMutation({
    mutationFn: (id: string) => api<void>(`/notifications/${id}/read/`, { method: 'POST' }),
    onSettled: refresh,
  })
  const readAll = useMutation({
    mutationFn: () => api<void>('/notifications/read-all/', { method: 'POST' }),
    onSettled: refresh,
  })

  function open(n: AppNotification) {
    if (!n.is_read) readOne.mutate(n.id)
    if (n.params.product) navigate(`/products/${n.params.product}`)
  }

  const status = (n: AppNotification) =>
    n.resolved_at ? (
      <Badge variant="secondary">{t('notifications.resolved')}</Badge>
    ) : !n.is_read ? (
      <Badge>{t('notifications.new')}</Badge>
    ) : null

  const columns: Column<AppNotification>[] = [
    {
      header: t('notifications.message'),
      cell: (n) => {
        const Icon = ICONS[n.kind]
        return (
          <span className={cn('flex items-center gap-2', !n.is_read && !n.resolved_at && 'font-medium')}>
            <Icon className="text-muted-foreground size-4 shrink-0" />
            {text(n)}
          </span>
        )
      },
    },
    { header: t('common.when'), cell: (n) => <span className="whitespace-nowrap">{formatDateTime(n.created_at)}</span> },
    { header: t('common.status'), cell: status, className: 'text-right' },
  ]

  return (
    <div className="mx-auto grid max-w-4xl gap-4">
      <PageHeader
        title={t('notifications.title')}
        description={t('notifications.subtitle')}
        actions={
          <Button size="lg" variant="outline" onClick={() => readAll.mutate()} disabled={readAll.isPending}>
            <CheckCheckIcon />
            {t('notifications.markAllRead')}
          </Button>
        }
      />

      <div className="flex flex-wrap gap-2" role="group" aria-label={t('notifications.show')}>
        {(['all', 'unread'] as const).map((value) => (
          <Button
            key={value}
            size="sm"
            variant={(value === 'unread') === onlyUnread ? 'default' : 'outline'}
            aria-pressed={(value === 'unread') === onlyUnread}
            onClick={() => list.set('show', value === 'unread' ? 'unread' : '')}
          >
            {t(`notifications.show_${value}`)}
          </Button>
        ))}
      </div>

      <DataList
        label={t('notifications.listLabel')}
        query={query}
        columns={columns}
        rowKey={(n) => n.id}
        onRowClick={open}
        page={list.page}
        onPageChange={list.setPage}
        empty={
          onlyUnread
            ? { title: t('notifications.allRead') }
            : { title: t('notifications.empty'), description: t('notifications.emptyText') }
        }
        card={(n) => {
          const Icon = ICONS[n.kind]
          return (
            <button type="button" className="w-full text-left" onClick={() => open(n)}>
              <Card className="gap-1 p-3 text-sm">
                <div className="flex items-start gap-2">
                  <Icon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
                  <span className={cn('flex-1', !n.is_read && !n.resolved_at && 'font-medium')}>{text(n)}</span>
                  {status(n)}
                </div>
                <span className="text-muted-foreground pl-6 text-xs">{formatDateTime(n.created_at)}</span>
              </Card>
            </button>
          )
        }}
      />
    </div>
  )
}
