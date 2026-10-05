import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { AppShell } from './app-shell'
import { AuthContext } from '@/lib/auth-context'
import type { AuthContextValue } from '@/lib/auth-context'
import { ME } from '@/test/fetch-mock'

function renderShell() {
  const auth: AuthContextValue = {
    status: 'authenticated',
    me: ME,
    error: null,
    retry: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(async () => {}),
    can: () => true,
  }
  const router = createMemoryRouter(
    [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <h1>Dashboard page</h1> },
          { path: '/settings', element: <h1>Settings page</h1> },
        ],
      },
      { path: '/login', element: <h1>Login page</h1> },
    ],
    { initialEntries: ['/'] },
  )
  render(
    <AuthContext.Provider value={auth}>
      <RouterProvider router={router} />
    </AuthContext.Provider>,
  )
  return auth
}

describe('AppShell mobile menu', () => {
  it('opens the sidebar as a drawer and closes it after navigating', async () => {
    renderShell()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Open menu' }))
    const drawer = await screen.findByRole('dialog', { name: 'Menu' })
    await user.click(within(drawer).getByRole('link', { name: 'Settings' }))

    expect(await screen.findByRole('heading', { name: 'Settings page' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Menu' })).not.toBeInTheDocument()
  })

  it('offers log out from the drawer', async () => {
    const auth = renderShell()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Open menu' }))
    const drawer = await screen.findByRole('dialog', { name: 'Menu' })
    await user.click(within(drawer).getByRole('button', { name: 'Log out' }))

    expect(auth.logout).toHaveBeenCalledOnce()
    expect(await screen.findByRole('heading', { name: 'Login page' })).toBeInTheDocument()
  })
})
