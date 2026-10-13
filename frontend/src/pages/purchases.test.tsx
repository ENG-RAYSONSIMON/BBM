import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PurchaseDetailPage } from './purchase-detail'
import { PurchaseFormPage } from './purchase-form'
import { PurchasesPage } from './purchases'
import { mockFetch } from '@/test/fetch-mock'
import { EMPTY_PAGE, page, product, purchase } from '@/test/fixtures'
import { renderWithAuth } from '@/test/render'

const MANAGE = ['purchases.view', 'purchases.manage', 'catalog.view']

describe('PurchasesPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists purchases with their status and total', async () => {
    mockFetch({
      'GET /purchases/': { status: 200, body: page([purchase()]) },
      'GET /suppliers/': { status: 200, body: EMPTY_PAGE },
    })
    renderWithAuth('/purchases', { '/purchases': <PurchasesPage /> }, ['purchases.view', 'catalog.view'])

    const table = await screen.findByRole('table', { name: 'purchases' })
    expect(within(table).getByText('P-000003')).toBeInTheDocument()
    expect(within(table).getByText('Dar Cosmetics')).toBeInTheDocument()
    expect(within(table).getByText(/75,000/)).toBeInTheDocument()
    expect(within(table).getByText('Draft')).toBeInTheDocument()
    // No purchases.manage: no way to start one.
    expect(screen.queryByRole('link', { name: /New purchase/ })).not.toBeInTheDocument()
  })

  it('shows the empty state with a link to buy', async () => {
    mockFetch({
      'GET /purchases/': { status: 200, body: EMPTY_PAGE },
      'GET /suppliers/': { status: 200, body: EMPTY_PAGE },
    })
    renderWithAuth('/purchases', { '/purchases': <PurchasesPage /> }, MANAGE)
    expect(await screen.findByText('No purchases yet')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /New purchase/ }).length).toBeGreaterThan(0)
  })

  it('shows an error with a retry button', async () => {
    mockFetch({
      'GET /purchases/': { status: 500, body: null },
      'GET /suppliers/': { status: 200, body: EMPTY_PAGE },
    })
    renderWithAuth('/purchases', { '/purchases': <PurchasesPage /> }, ['purchases.view'])
    expect(await screen.findByText('Something went wrong on our side. Please try again.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('PurchaseFormPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  const ROUTES = { '/purchases/new': <PurchaseFormPage />, '/purchases/:id': <p>Purchase page</p> }
  const PADS = product({ id: 'p2', name: 'Cotton Pads', tracks_expiry: false, cost_price: '1500.00' })

  it('totals the lines, asks for batch details only when expiry is tracked, and sends a clean body', async () => {
    const fetchMock = mockFetch({
      'GET /products/': { status: 200, body: page([product(), PADS]) },
      'GET /suppliers/': { status: 200, body: EMPTY_PAGE },
      'POST /purchases/': { status: 201, body: purchase() },
    })
    renderWithAuth('/purchases/new', ROUTES, MANAGE)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Add Cotton Pads' }))
    await user.click(screen.getByRole('button', { name: 'Add Cotton Pads' })) // same line, quantity 2
    expect(screen.getByLabelText('Quantity of Cotton Pads')).toHaveValue('2')
    expect(screen.queryByLabelText('Batch number of Cotton Pads')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add Shea Butter' }))
    const save = screen.getByRole('button', { name: 'Save draft' })
    expect(screen.getByText('Enter the batch number on the stock.')).toBeInTheDocument()
    expect(save).toBeDisabled()

    await user.type(screen.getByLabelText('Batch number of Shea Butter'), 'SB-01')
    await user.type(screen.getByLabelText('Expiry date of Shea Butter'), '2027-06-30')
    const cost = screen.getByLabelText('Unit cost (TZS) of Shea Butter')
    await user.clear(cost)
    await user.type(cost, '7500')
    const quantity = screen.getByLabelText('Quantity of Shea Butter')
    await user.clear(quantity)
    await user.type(quantity, '10')
    expect(screen.getByLabelText('Total')).toHaveTextContent('78,000') // 2 × 1,500 + 10 × 7,500

    await user.click(save)
    expect(await screen.findByText('Purchase page')).toBeInTheDocument()
    const body = JSON.parse(String(fetchMock.calls.find((c) => c.key === 'POST /purchases/')!.init.body))
    expect(body.items).toEqual([
      { product: 'p2', quantity: 2, unit_cost: '1500.00', batch_number: '', expiry_date: null },
      { product: 'p1', quantity: 10, unit_cost: '7500.00', batch_number: 'SB-01', expiry_date: '2027-06-30' },
    ])
    expect(body.supplier).toBeNull()
    expect(fetchMock.count('POST /purchases/pu1/receive/')).toBe(0)
  })

  it('shows the server error and keeps the form', async () => {
    mockFetch({
      'GET /products/': { status: 200, body: page([PADS]) },
      'GET /suppliers/': { status: 200, body: EMPTY_PAGE },
      'POST /purchases/': { status: 400, body: { items: ['Cotton Pads is archived. Reactivate it before buying more.'] } },
    })
    renderWithAuth('/purchases/new', ROUTES, MANAGE)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Add Cotton Pads' }))
    await user.click(screen.getByRole('button', { name: 'Save & receive' }))
    expect(await screen.findByText('Cotton Pads is archived. Reactivate it before buying more.')).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity of Cotton Pads')).toBeInTheDocument()
  })
})

describe('PurchaseDetailPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  const ROUTES = { '/purchases/:id': <PurchaseDetailPage /> }

  it('receives a draft after confirmation', async () => {
    const received = purchase({ status: 'RECEIVED', received_at: '2026-10-12T09:00:00Z', received_by_name: 'Amina' })
    const fetchMock = mockFetch({
      'GET /purchases/pu1/': { status: 200, body: purchase() },
      'POST /purchases/pu1/receive/': { status: 200, body: received },
    })
    renderWithAuth('/purchases/pu1', ROUTES, MANAGE)
    const user = userEvent.setup()

    expect(await screen.findByText(/This purchase is a draft/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Receive' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Receive stock' }))

    expect(await screen.findByText(/The stock is on the shelf/)).toBeInTheDocument()
    expect(fetchMock.count('POST /purchases/pu1/receive/')).toBe(1)
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Receive' })).not.toBeInTheDocument())
  })

  it('offers no actions without purchases.manage or once received', async () => {
    mockFetch({ 'GET /purchases/pu1/': { status: 200, body: purchase() } })
    renderWithAuth('/purchases/pu1', ROUTES, ['purchases.view'])
    expect(await screen.findByText('P-000003')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Receive' })).not.toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('hides draft actions on a received purchase', async () => {
    mockFetch({ 'GET /purchases/pu1/': { status: 200, body: purchase({ status: 'RECEIVED' }) } })
    renderWithAuth('/purchases/pu1', ROUTES, MANAGE)
    expect(await screen.findByText('Received')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Receive' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()
  })

  it('needs a reason to cancel and shows server errors', async () => {
    mockFetch({
      'GET /purchases/pu1/': { status: 200, body: purchase() },
      'POST /purchases/pu1/cancel/': { status: 400, body: { non_field_errors: ['Only a draft purchase can be cancelled.'] } },
    })
    renderWithAuth('/purchases/pu1', ROUTES, MANAGE)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Cancel purchase' }))
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Cancel purchase' }))
    expect(await within(dialog).findByText('Say why the purchase is being cancelled.')).toBeInTheDocument()

    await user.type(within(dialog).getByLabelText('Reason'), 'Supplier out of stock')
    await user.click(within(dialog).getByRole('button', { name: 'Cancel purchase' }))
    expect(await within(dialog).findByText('Only a draft purchase can be cancelled.')).toBeInTheDocument()
  })
})
