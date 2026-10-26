import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from 'next-themes'
import { useTranslation } from 'react-i18next'
import { createBrowserRouter, Link, RouterProvider } from 'react-router'

import { AppShell } from '@/components/layout/app-shell'
import { AuthLayout } from '@/components/layout/auth-layout'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider } from '@/lib/auth'
import { DashboardPage } from '@/pages/dashboard'
import { ForgotPasswordPage } from '@/pages/forgot-password'
import { LoginPage } from '@/pages/login'
import { ProductFormPage } from '@/pages/product-form'
import { RegisterPage } from '@/pages/register'
import { ResetPasswordPage } from '@/pages/reset-password'
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
          // Other pages load on first visit, keeping the initial bundle small.
          { path: '/pos', lazy: () => import('@/pages/pos').then((m) => ({ Component: m.PosPage })) },
          { path: '/sales', lazy: () => import('@/pages/sales').then((m) => ({ Component: m.SalesPage })) },
          {
            path: '/sales/:id',
            lazy: () => import('@/pages/sale-detail').then((m) => ({ Component: m.SaleDetailPage })),
          },
          { path: '/customers', lazy: () => import('@/pages/customers').then((m) => ({ Component: m.CustomersPage })) },
          { path: '/purchases', lazy: () => import('@/pages/purchases').then((m) => ({ Component: m.PurchasesPage })) },
          {
            path: '/purchases/new',
            lazy: () => import('@/pages/purchase-form').then((m) => ({ Component: m.PurchaseFormPage })),
          },
          {
            path: '/purchases/:id',
            lazy: () => import('@/pages/purchase-detail').then((m) => ({ Component: m.PurchaseDetailPage })),
          },
          {
            path: '/purchases/:id/edit',
            lazy: () => import('@/pages/purchase-form').then((m) => ({ Component: m.PurchaseFormPage })),
          },
          { path: '/expenses', lazy: () => import('@/pages/expenses').then((m) => ({ Component: m.ExpensesPage })) },
          { path: '/products', lazy: () => import('@/pages/products').then((m) => ({ Component: m.ProductsPage })) },
          // The form stays eager: `key` remounts it when switching new ↔ edit.
          { path: '/products/new', element: <ProductFormPage /> },
          {
            path: '/products/:id',
            lazy: () => import('@/pages/product-detail').then((m) => ({ Component: m.ProductDetailPage })),
          },
          { path: '/products/:id/edit', element: <ProductFormPage key="edit" /> },
          { path: '/inventory', lazy: () => import('@/pages/inventory').then((m) => ({ Component: m.InventoryPage })) },
          { path: '/catalog', lazy: () => import('@/pages/catalog').then((m) => ({ Component: m.CatalogPage })) },
          { path: '/settings', lazy: () => import('@/pages/settings').then((m) => ({ Component: m.SettingsPage })) },
          { path: '/reports', lazy: () => import('@/pages/reports').then((m) => ({ Component: m.ReportsPage })) },
          { path: '/audit', lazy: () => import('@/pages/audit').then((m) => ({ Component: m.AuditPage })) },
        ],
      },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
])

function NotFoundPage() {
  const { t } = useTranslation()
  return (
    <AuthLayout title={t('common.pageNotFound')} description={t('common.pageNotFoundText')}>
      <Link to="/" className="font-medium underline-offset-4 hover:underline">
        {t('common.goToDashboard')}
      </Link>
    </AuthLayout>
  )
}

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
