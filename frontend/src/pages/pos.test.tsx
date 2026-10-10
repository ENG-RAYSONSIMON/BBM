import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PosPage } from './pos'
import { mockFetch } from '@/test/fetch-mock'
import { page, product, sale } from '@/test/fixtures'
import { renderWithAuth } from '@/test/render'

const ROUTES = { '/pos': <PosPage />, '/sales/:id': <p>Receipt</p> }
const PERMS = ['sales.view', 'sales.create']

describe('PosPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('totals the cart, shows the change and sends only ids, quantities and cash', async () => {
    const fetchMock = mockFetch({
      'GET /products/': { status: 200, body: page([product()]) },
      'POST /sales/': { status: 201, body: sale() },
    })
    renderWithAuth('/pos', ROUTES, PERMS)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Add Shea Butter' }))
    await user.click(screen.getByRole('button', { name: 'Add Shea Butter' }))
    expect(screen.getByLabelText('Quantity of Shea Butter')).toHaveValue('2')
    await user.type(screen.getByLabelText('Discount (TZS)'), '1000')
    expect(screen.getByLabelText('Total')).toHaveTextContent('29,000')

    await user.type(screen.getByLabelText('Cash received'), '30000')
    expect(screen.getByText(/Change to give:.*1,000/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Complete sale/ }))
    expect(await screen.findByText('Receipt')).toBeInTheDocument()
    const body = JSON.parse(String(fetchMock.calls.find((c) => c.key === 'POST /sales/')!.init.body))
    expect(body).toEqual({
      items: [{ product: 'p1', quantity: 2, discount: '1000.00' }],
      amount_received: '30000.00',
      note: '',
    })
  })

  it('needs a customer when cash is short, then shows the server stock error', async () => {
    const fetchMock = mockFetch({
      'GET /products/': { status: 200, body: page([product()]) },
      'POST /sales/': { status: 400, body: { items: ['Shea Butter: only 1 available to sell.'] } },
    })
    renderWithAuth('/pos', ROUTES, PERMS)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Add Shea Butter' }))
    await user.type(screen.getByLabelText('Cash received'), '5000')
    expect(screen.getByText(/10,000 will be owed on credit/)).toBeInTheDocument()
    expect(screen.getByText('Choose or add the customer who owes the balance.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Complete sale/ })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'New customer' }))
    await user.type(screen.getByLabelText('Name'), 'Mama Asha')
    await user.click(screen.getByRole('button', { name: /Complete sale/ }))

    expect(await screen.findByText('Shea Butter: only 1 available to sell.')).toBeInTheDocument()
    const body = JSON.parse(String(fetchMock.calls.find((c) => c.key === 'POST /sales/')!.init.body))
    expect(body.new_customer).toEqual({ name: 'Mama Asha', phone: '' })
    expect(body.amount_received).toBe('5000.00')
  })

  it('does not offer out-of-stock products', async () => {
    mockFetch({ 'GET /products/': { status: 200, body: page([product({ stock_on_hand: 0 })]) } })
    renderWithAuth('/pos', ROUTES, PERMS)
    expect(await screen.findByRole('button', { name: 'Add Shea Butter' })).toBeDisabled()
    expect(screen.getByText(/Out of stock/)).toBeInTheDocument()
  })
})
