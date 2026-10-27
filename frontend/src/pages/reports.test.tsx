import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ReportsPage } from './reports'
import type { SalesReport, StockValuationReport } from '@/lib/types'
import { mockFetch } from '@/test/fetch-mock'
import { renderWithAuth } from '@/test/render'

const SALES: SalesReport = {
  period: 'day',
  date_from: '2026-10-25',
  date_to: '2026-10-26',
  rows: [
    { period: '2026-10-25', sales_count: 0, revenue: '0.00', discounts: '0.00', cogs: '0.00', gross_profit: '0.00', cash_collected: '0.00' },
    { period: '2026-10-26', sales_count: 2, revenue: '24000.00', discounts: '0.00', cogs: '16000.00', gross_profit: '8000.00', cash_collected: '12000.00' },
  ],
  totals: { sales_count: 2, revenue: '24000.00', discounts: '0.00', cogs: '16000.00', gross_profit: '8000.00', cash_collected: '12000.00' },
}

const STOCK: StockValuationReport = {
  as_of: '2026-10-26',
  rows: [
    {
      product: 'p1', name: 'Shea Butter', sku: 'SB-1', category_name: 'Creams', unit: 'pcs', is_active: true,
      stock_on_hand: 10, cost_price: '8000.00', selling_price: '12000.00', cost_value: '80000.00', retail_value: '120000.00',
    },
  ],
  totals: { product_count: 1, stock_on_hand: 10, cost_value: '80000.00', retail_value: '120000.00' },
}

const ROUTES = { '/reports': <ReportsPage /> }

describe('ReportsPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the sales report with totals and a row per day', async () => {
    mockFetch({ 'GET /reports/sales/': { status: 200, body: SALES } })
    renderWithAuth('/reports', ROUTES, ['reports.view'])

    const table = await screen.findByRole('table', { name: 'Sales' })
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(within(table).getByText(/24,000/)).toBeInTheDocument()
    expect(screen.getByText('2 sales')).toBeInTheDocument()
    // No reports.export: no download.
    expect(screen.queryByRole('button', { name: /Download CSV/ })).not.toBeInTheDocument()
  })

  it('leaves out cost and profit without finance.view', async () => {
    const { cogs: _cogs, gross_profit: _profit, ...totals } = SALES.totals
    mockFetch({
      'GET /reports/sales/': {
        status: 200,
        body: { ...SALES, rows: SALES.rows.map(({ cogs: _c, gross_profit: _g, ...row }) => row), totals },
      },
    })
    renderWithAuth('/reports?report=profit', ROUTES, ['reports.view'])

    // Asking for the profit report by URL falls back to sales.
    const table = await screen.findByRole('table', { name: 'Sales' })
    expect(within(table).queryByText('Gross profit')).not.toBeInTheDocument()
    expect(screen.queryByText('Gross profit')).not.toBeInTheDocument()
    for (const name of ['Profit', 'Stock value', 'Expiry']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
    // Without expenses.view, no spending either.
    expect(screen.queryByRole('button', { name: 'Expenses' })).not.toBeInTheDocument()
  })

  it('shows the expenses report with expenses.view', async () => {
    mockFetch({ 'GET /reports/sales/': { status: 200, body: SALES } })
    renderWithAuth('/reports', ROUTES, ['reports.view', 'expenses.view'])
    await screen.findByRole('table', { name: 'Sales' })
    expect(screen.getByRole('button', { name: 'Expenses' })).toBeInTheDocument()
    // Profit needs finance.view as well.
    expect(screen.queryByRole('button', { name: 'Profit' })).not.toBeInTheDocument()
  })

  it('switches report and sends the chosen period', async () => {
    const mock = mockFetch({
      'GET /reports/sales/': { status: 200, body: SALES },
      'GET /reports/stock-valuation/': { status: 200, body: STOCK },
    })
    renderWithAuth('/reports', ROUTES, ['reports.view', 'finance.view'])
    await screen.findByRole('table', { name: 'Sales' })

    await userEvent.click(screen.getByRole('button', { name: 'Month' }))
    await waitFor(() => expect(mock.count('GET /reports/sales/')).toBe(2))
    const urls = vi.mocked(fetch).mock.calls.map(([input]) => String(input))
    expect(urls.at(-1)).toContain('period=month')

    await userEvent.click(screen.getByRole('button', { name: 'Stock value' }))
    const table = await screen.findByRole('table', { name: 'Stock value' })
    expect(within(table).getByText('Shea Butter')).toBeInTheDocument()
    expect(within(table).getByText(/80,000/)).toBeInTheDocument()
  })

  it('downloads the CSV with reports.export', async () => {
    const mock = mockFetch({
      'GET /reports/sales/': { status: 200, body: SALES },
      'GET /reports/sales/export/': { status: 200, body: 'csv' },
    })
    const createObjectURL = vi.fn(() => 'blob:report')
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    renderWithAuth('/reports', ROUTES, ['reports.view', 'reports.export'])

    await screen.findByRole('table', { name: 'Sales' })
    await userEvent.click(screen.getByRole('button', { name: /Download CSV/ }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    expect(mock.count('GET /reports/sales/export/')).toBe(1)
    expect(createObjectURL).toHaveBeenCalled()
    click.mockRestore()
  })

  it('shows an error with a retry button', async () => {
    mockFetch({ 'GET /reports/sales/': { status: 400, body: { period: ['That is too many days. Show it by week, month or year instead.'] } } })
    renderWithAuth('/reports', ROUTES, ['reports.view'])
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
