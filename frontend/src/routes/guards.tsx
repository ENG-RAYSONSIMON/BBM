import { Navigate, Outlet, useLocation } from 'react-router'

import { FullPageError, FullPageLoading } from '@/components/full-page-status'
import { useAuth } from '@/lib/auth-context'

/** Pages for logged-in users. Anonymous visitors go to /login and come back after. */
export function RequireAuth() {
  const { status, error, retry } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <FullPageLoading />
  if (status === 'error') {
    return <FullPageError message={error?.message ?? 'Could not load your account.'} onRetry={retry} />
  }
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: location }} />
  return <Outlet />
}

/** Login/register pages: a logged-in user goes straight to the app. */
export function RedirectIfAuthed() {
  const { status } = useAuth()

  if (status === 'loading') return <FullPageLoading />
  if (status === 'authenticated') return <Navigate to="/" replace />
  return <Outlet />
}
