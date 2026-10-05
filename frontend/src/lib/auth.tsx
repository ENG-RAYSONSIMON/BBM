import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'

import { api, ApiError, onAuthLost, tokenStore } from './api'
import { AuthContext } from './auth-context'
import type { AuthContextValue, AuthStatus, LoginInput, RegisterInput } from './auth-context'
import type { AuthPayload, Me } from './types'

const ME_QUERY_KEY = ['me'] as const

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [hasSession, setHasSession] = useState(() => tokenStore.getRefresh() !== null)

  const meQuery = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: () => api<Me>('/auth/me/'),
    enabled: hasSession,
    retry: false,
    staleTime: 60_000,
  })

  const endSession = useCallback(() => {
    tokenStore.clear()
    queryClient.clear()
    setHasSession(false)
  }, [queryClient])

  useEffect(() => {
    onAuthLost(() => {
      endSession()
      toast.info('Your session has ended. Please log in again.')
    })
    // Logging out in another tab removes the shared refresh token.
    const onStorage = (event: StorageEvent) => {
      if (event.key === tokenStore.REFRESH_KEY && event.newValue === null) endSession()
    }
    window.addEventListener('storage', onStorage)
    return () => {
      onAuthLost(null)
      window.removeEventListener('storage', onStorage)
    }
  }, [endSession])

  const startSession = useCallback(
    async (payload: AuthPayload) => {
      tokenStore.set(payload)
      await queryClient.fetchQuery({
        queryKey: ME_QUERY_KEY,
        queryFn: () => api<Me>('/auth/me/'),
      })
      setHasSession(true)
    },
    [queryClient],
  )

  const login = useCallback(
    async (input: LoginInput) => {
      await startSession(await api<AuthPayload>('/auth/login/', { method: 'POST', body: input, auth: false }))
    },
    [startSession],
  )

  const register = useCallback(
    async (input: RegisterInput) => {
      await startSession(
        await api<AuthPayload>('/auth/register/', { method: 'POST', body: input, auth: false }),
      )
    },
    [startSession],
  )

  const logout = useCallback(async () => {
    const refresh = tokenStore.getRefresh()
    if (refresh) {
      // Best effort: the session ends locally even if the server is unreachable.
      await api('/auth/logout/', { method: 'POST', body: { refresh } }).catch(() => undefined)
    }
    endSession()
  }, [endSession])

  let status: AuthStatus
  if (!hasSession) status = 'anonymous'
  else if (meQuery.isSuccess) status = 'authenticated'
  else if (meQuery.isError)
    status = meQuery.error instanceof ApiError && meQuery.error.status === 401 ? 'anonymous' : 'error'
  else status = 'loading'

  const me = meQuery.data
  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      me,
      error: meQuery.error,
      retry: () => void meQuery.refetch(),
      login,
      register,
      logout,
      can: (permission) => me?.permissions.includes(permission) ?? false,
    }),
    [status, me, meQuery, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
