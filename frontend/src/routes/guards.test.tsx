import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { CHANGE_PASSWORD_PATH, RequireAuth } from './guards'
import { AuthContext } from '@/lib/auth-context'
import type { AuthContextValue } from '@/lib/auth-context'
import { ME } from '@/test/fetch-mock'

function renderGuarded(path: string, mustChange: boolean) {
  const auth: AuthContextValue = {
    status: 'authenticated',
    me: { ...ME, user: { ...ME.user, must_change_password: mustChange } },
    error: null,
    retry: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
    can: () => true,
  }
  const router = createMemoryRouter(
    [
      {
        element: <RequireAuth />,
        children: [
          { path: '/sales', element: <p>Sales page</p> },
          { path: CHANGE_PASSWORD_PATH, element: <p>Choose a password</p> },
        ],
      },
    ],
    { initialEntries: [path] },
  )
  render(
    <AuthContext.Provider value={auth}>
      <RouterProvider router={router} />
    </AuthContext.Provider>,
  )
  return router
}

describe('RequireAuth', () => {
  it('sends someone on a temporary password to choose their own first', async () => {
    const router = renderGuarded('/sales', true)
    expect(await screen.findByText('Choose a password')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(CHANGE_PASSWORD_PATH)
  })

  it('lets everyone else through', async () => {
    renderGuarded('/sales', false)
    expect(await screen.findByText('Sales page')).toBeInTheDocument()
  })
})
