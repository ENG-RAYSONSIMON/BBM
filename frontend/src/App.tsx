import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from 'next-themes'
import { createBrowserRouter, Link, RouterProvider } from 'react-router'

import { AppShell } from '@/components/layout/app-shell'
import { AuthLayout } from '@/components/layout/auth-layout'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider } from '@/lib/auth'
import { DashboardPage } from '@/pages/dashboard'
import { ForgotPasswordPage } from '@/pages/forgot-password'
import { LoginPage } from '@/pages/login'
import { RegisterPage } from '@/pages/register'
import { ResetPasswordPage } from '@/pages/reset-password'
import { SettingsPage } from '@/pages/settings'
import { RedirectIfAuthed, RequireAuth } from '@/routes/guards'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

const router = createBrowserRouter([
  {
    element: <RedirectIfAuthed />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/register', element: <RegisterPage /> },
      { path: '/forgot-password', element: <ForgotPasswordPage /> },
    ],
  },
  // Reachable whether or not someone is logged in (the link comes by email).
  { path: '/reset-password', element: <ResetPasswordPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: '/settings', element: <SettingsPage /> },
        ],
      },
    ],
  },
  {
    path: '*',
    element: (
      <AuthLayout title="Page not found" description="That page doesn't exist.">
        <Link to="/" className="font-medium underline-offset-4 hover:underline">
          Go to the dashboard
        </Link>
      </AuthLayout>
    ),
  },
])

export default function App() {
  return (
    // Adds .dark to <html>; the choice is saved in localStorage ("bbm.theme").
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem storageKey="bbm.theme" disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RouterProvider router={router} />
          <Toaster position="top-center" richColors closeButton />
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
