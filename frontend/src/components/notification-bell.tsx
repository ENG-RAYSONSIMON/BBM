import { useQuery } from '@tanstack/react-query'
import { BellIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'

/** Bell linking to the notification centre, with the open alerts not yet read. Polls every minute. */
export function NotificationBell({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation()
  const { data } = useQuery({
    // Under the 'notifications' prefix, so marking read refreshes the count too.
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => api<{ unread: number }>('/notifications/unread-count/'),
    refetchInterval: 60_000,
  })
  const unread = data?.unread ?? 0
  return (
    <Button asChild variant="ghost" size="icon-lg" className="relative">
      <Link
        to="/notifications"
        onClick={onNavigate}
        aria-label={unread ? t('notifications.bellUnread', { count: unread }) : t('notifications.title')}
      >
        <BellIcon />
        {unread > 0 && (
          <span className="bg-destructive absolute -top-0.5 -right-0.5 min-w-4 rounded-full px-1 text-center text-[10px] leading-4 font-semibold text-white tabular-nums">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </Link>
    </Button>
  )
}
