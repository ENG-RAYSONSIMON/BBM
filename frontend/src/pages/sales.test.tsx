import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SaleDetailPage } from './sale-detail'
import { SalesPage } from './sales'
import { mockFetch } from '@/test/fetch-mock'
import { EMPTY_PAGE, page, sale } from '@/test/fixtures'
import { renderWithAuth } from '@/test/render'

describe('SalesPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists sales with what is still owed', async () => {
    mockFetch({ 'GET /sales/': { status: 200, body: page([sale()]) } })
    renderWithAuth('/sales', { '/sales': <SalesPage /> }, ['sales.view'])

    const table = await screen.findByRole('table', { name: 'sales' })
    expect(within(table).getByText('S-000007')).toBeInTheDocument()
    expect(within(table).getByText('Mama Asha')).toBeInTheDocument()
    expect(within(table).getByText(/20,000/)).toBeInTheDocument()
    expect(within(table).getByText('Part paid')).toBeInTheDocument()
    // No sales.create: no way to start a sale from here.
    expect(screen.queryByRole('link', { name: /New sale/ })).not.toBeInTheDocument()
  })

  it('shows the empty state with a link to sell', async () => {
    mockFetch({ 'GET /sales/': { status: 200, body: EMPTY_PAGE } })
    renderWithAuth('/sales', { '/sales': <SalesPage /> }, ['sales.view', 'sales.create'])
    expect(await screen.findByText('No sales yet')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /New sale/ }).length).toBeGreaterThan(0)
  })

  it('shows an error with a retry button', async () => {
    mockFetch({ 'GET /sales/': { status: 500, body: null } })
    renderWithAuth('/sales', { '/sales': <SalesPage /> }, ['sales.view'])
    expect(await screen.findByText('Something went wrong on our side. Please try again.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('SaleDetailPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('records a repayment and shows the change to give', async () => {
    const fetchMock = mockFetch({
      'GET /sales/s1/': [
        { status: 200, body: sale() },
        { status: 200, body: sale({ amount_paid: '30000.00', balance: '0.00', payment_status: 'PAID' }) },
      ],
      'POST /sales/s1/payments/': { status: 201, body: {} },
    })
    renderWithAuth('/sales/s1', { '/sales/:id': <SaleDetailPage /> }, ['sales.view', 'sales.create'])
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Record payment' }))
    const dialog = screen.getByRole('dialog')
    await user.type(within(dialog).getByLabelText('Cash received'), '25000')
    expect(within(dialog).getByText(/Give back .*5,000 change/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Record payment' }))

    // Refetched as fully paid: nothing left to collect.
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Record payment' })).not.toBeInTheDocument())
    expect(fetchMock.count('GET /sales/s1/')).toBe(2)
    const body = JSON.parse(String(fetchMock.calls.find((c) => c.key === 'POST /sales/s1/payments/')!.init.body))
    expect(body).toEqual({ amount_received: '25000', note: '' })
  })

  it('only offers void to roles with sales.void', async () => {
    mockFetch({ 'GET /sales/s1/': { status: 200, body: sale() } })
    renderWithAuth('/sales/s1', { '/sales/:id': <SaleDetailPage /> }, ['sales.view', 'sales.create'])
    expect(await screen.findByText('S-000007')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Void' })).not.toBeInTheDocument()
  })

  it('requires a reason to void and shows server errors', async () => {
    mockFetch({
      'GET /sales/s1/': { status: 200, body: sale() },
      'POST /sales/s1/void/': { status: 400, body: { non_field_errors: ['This sale is already void.'] } },
    })
    renderWithAuth('/sales/s1', { '/sales/:id': <SaleDetailPage /> }, ['sales.view', 'sales.void'])
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Void' }))
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Void sale' }))
    expect(await within(dialog).findByText('Say why the sale is being voided.')).toBeInTheDocument()

    await user.type(within(dialog).getByLabelText('Reason'), 'Returned')
    await user.click(within(dialog).getByRole('button', { name: 'Void sale' }))
    expect(await within(dialog).findByText('This sale is already void.')).toBeInTheDocument()
  })
})
