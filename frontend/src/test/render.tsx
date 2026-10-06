import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'

import { AuthProvider } from '@/lib/auth'
import { AuthContext } from '@/lib/auth-context'
import type { AuthContextValue } from '@/lib/auth-context'
import { ME } from '@/test/fetch-mock'

/** Render `element` at `path` with providers; "/" renders a "Home" marker. */
export function renderRoute(path: string, element: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(
    [
      { path, element },
      { path: '/', element: <p>Home</p> },
    ],
    { initialEntries: [path] },
  )
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

/**
 * Render routes inside a fake signed-in session with exactly `permissions`.
 * `routes` maps paths to elements; "/" always renders a "Home" marker.
 */
export function renderWithAuth(
  path: string,
  routes: Record<string, ReactElement>,
  permissions: string[],
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const auth: AuthContextValue = {
    status: 'authenticated',
    me: { ...ME, permissions },
    error: null,
    retry: () => {},
    login: async () => {},
    register: async () => {},
    logout: async () => {},
    can: (permission) => permissions.includes(permission),
  }
  const router = createMemoryRouter(
    [
      { path: '/', element: <p>Home</p> },
      ...Object.entries(routes).map(([routePath, element]) => ({ path: routePath, element })),
    ],
    { initialEntries: [path] },
  )
  render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={auth}>
        <RouterProvider router={router} />
      </AuthContext.Provider>
    </QueryClientProvider>,
  )
  return { router, queryClient }
}
