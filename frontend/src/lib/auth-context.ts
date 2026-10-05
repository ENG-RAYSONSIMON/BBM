import { createContext, useContext } from 'react'

import type { Me } from './types'

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous' | 'error'

export type LoginInput = { email: string; password: string; business_id?: string }
export type RegisterInput = {
  email: string
  password: string
  business_name: string
  first_name?: string
  last_name?: string
  phone?: string
}

export type AuthContextValue = {
  status: AuthStatus
  me: Me | undefined
  error: Error | null
  retry: () => void
  login: (input: LoginInput) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => Promise<void>
  can: (permission: string) => boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>.')
  return ctx
}
