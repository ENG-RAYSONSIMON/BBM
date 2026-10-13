import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardPage } from './dashboard'
import { mockFetch } from '@/test/fetch-mock'
import { renderWithAuth } from '@/test/render'

const SUMMARY = {
  date_from: '2026-10-10',
  date_to: '2026-10-10',
  sales_count: 3,
  revenue: '45000.00',
  discounts: '0.00',
  cogs: '27000.00',
  gross_profit: '18000.00',
  cash_collected: '40000.00',
  outstanding_credit: '12500.00',
  expenses: '5000.00',
  net_profit: '13000.00',
}

describe('DashboardPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it("shows today's sales, profit, cash and credit from the summary", async () => {
    mockFetch({ 'GET /sales/summary/': { status: 200, body: SUMMARY } })
    renderWithAuth('/dash', { '/dash': <DashboardPage /> }, ['sales.view'])

    expect(await screen.findByText('3 sales')).toBeInTheDocument()
    expect(screen.getByText(/45,000/)).toBeInTheDocument()
    expect(screen.getByText(/18,000/)).toBeInTheDocument()
    expect(screen.getByText(/40,000/)).toBeInTheDocument()
    expect(screen.getByText(/12,500/)).toBeInTheDocument()
  })

  it('shows expenses and net profit with expenses.view, and switches period', async () => {
    const fetchMock = mockFetch({ 'GET /sales/summary/': { status: 200, body: SUMMARY } })
    renderWithAuth('/dash', { '/dash': <DashboardPage /> }, ['sales.view', 'expenses.view'])

    expect(await screen.findByText("Today's net profit")).toBeInTheDocument()
    expect(await screen.findByText(/13,000/)).toBeInTheDocument()
    expect(screen.getByText(/\D5,000$/)).toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole('button', { name: 'This month' }))
    expect(await screen.findByText("This month's net profit")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'This month' })).toHaveAttribute('aria-pressed', 'true')
    expect(fetchMock.count('GET /sales/summary/')).toBe(2)
  })

  it('hides expense tiles without expenses.view', async () => {
    mockFetch({ 'GET /sales/summary/': { status: 200, body: { ...SUMMARY, expenses: null, net_profit: null } } })
    renderWithAuth('/dash', { '/dash': <DashboardPage /> }, ['sales.view'])
    expect(await screen.findByText('3 sales')).toBeInTheDocument()
    expect(screen.queryByText(/net profit/)).not.toBeInTheDocument()
    expect(screen.queryByText("Today's expenses")).not.toBeInTheDocument()
  })

  it('hides sales figures without sales.view', async () => {
    const fetchMock = mockFetch({})
    renderWithAuth('/dash', { '/dash': <DashboardPage /> }, [])
    expect(await screen.findByText(/Welcome/)).toBeInTheDocument()
    expect(screen.queryByText("Today's sales")).not.toBeInTheDocument()
    expect(fetchMock.calls).toHaveLength(0)
  })
})
