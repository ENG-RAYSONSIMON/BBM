import { useTranslation } from 'react-i18next'
import { Navigate, Outlet, useLocation } from 'react-router'

import { FullPageError, FullPageLoading } from '@/components/full-page-status'
import { useAuth } from '@/lib/auth-context'

export const CHANGE_PASSWORD_PATH = '/change-password'

/**
 * Pages for logged-in users. Anonymous visitors go to /login and come back
 * after. Someone on a temporary password must choose their own first (the
 * server refuses everything else until then).
 */
export function RequireAuth() {
  const { status, me, error, retry } = useAuth()
  const location = useLocation()
  const { t } = useTranslation()

  if (status === 'loading') return <FullPageLoading />
  if (status === 'error') {
    return <FullPageError message={error?.message ?? t('common.couldNotLoadAccount')} onRetry={retry} />
  }
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: location }} />
  if (me?.user.must_change_password && location.pathname !== CHANGE_PASSWORD_PATH) {
    return <Navigate to={CHANGE_PASSWORD_PATH} replace />
  }
  return <Outlet />
}

/** Login/register pages: a logged-in user goes straight to the app. */
export function RedirectIfAuthed() {
  const { status } = useAuth()

  if (status === 'loading') return <FullPageLoading />
  if (status === 'authenticated') return <Navigate to="/" replace />
  return <Outlet />
}
