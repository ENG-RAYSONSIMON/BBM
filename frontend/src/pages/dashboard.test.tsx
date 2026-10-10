import { screen } from '@testing-library/react'
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

  it('hides sales figures without sales.view', async () => {
    const fetchMock = mockFetch({})
    renderWithAuth('/dash', { '/dash': <DashboardPage /> }, [])
    expect(await screen.findByText(/Welcome/)).toBeInTheDocument()
    expect(screen.queryByText("Today's sales")).not.toBeInTheDocument()
    expect(fetchMock.calls).toHaveLength(0)
  })
})
