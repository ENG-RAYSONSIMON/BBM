import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ExpensesPage } from './expenses'
import { mockFetch } from '@/test/fetch-mock'
import { EMPTY_PAGE, EXPENSE_CATEGORIES, expense, page } from '@/test/fixtures'
import { renderWithAuth } from '@/test/render'

const ROUTES = { '/expenses': <ExpensesPage /> }
const SUMMARY = {
  date_from: '2026-10-01',
  date_to: '2026-10-12',
  total: '58000.00',
  count: 2,
  by_category: [
    { category: 'cat-rent', category_name: 'Rent', total: '50000.00', count: 1 },
    { category: 'cat-transport', category_name: 'Transport', total: '8000.00', count: 1 },
  ],
}

function routes(list: unknown = page([expense()]), extra: Record<string, unknown> = {}) {
  return {
    'GET /expenses/': { status: 200, body: list },
    'GET /expenses/summary/': { status: 200, body: SUMMARY },
    'GET /expense-categories/': { status: 200, body: EXPENSE_CATEGORIES },
    ...extra,
  } as Parameters<typeof mockFetch>[0]
}

describe('ExpensesPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it("lists expenses with the month's total by category", async () => {
    mockFetch(routes())
    renderWithAuth('/expenses', ROUTES, ['expenses.view'])

    const table = await screen.findByRole('table', { name: 'expenses' })
    expect(within(table).getByText('October rent')).toBeInTheDocument()
    expect(within(table).getByText(/50,000/)).toBeInTheDocument()
    expect(screen.getByLabelText('Period total')).toHaveTextContent('58,000')
    expect(within(screen.getByRole('list', { name: 'By category' })).getByText(/8,000/)).toBeInTheDocument()
    // View only: nothing to add.
    expect(screen.queryByRole('button', { name: /Add expense/ })).not.toBeInTheDocument()
  })

  it('shows the empty state and an error state', async () => {
    mockFetch(routes(EMPTY_PAGE))
    renderWithAuth('/expenses', ROUTES, ['expenses.view', 'expenses.manage'])
    expect(await screen.findByText('No expenses yet')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('shows an error with a retry button', async () => {
    mockFetch({ ...routes(), 'GET /expenses/': { status: 500, body: null } })
    renderWithAuth('/expenses', ROUTES, ['expenses.view'])
    expect(await screen.findByText('Something went wrong on our side. Please try again.')).toBeInTheDocument()
  })

  it('validates a new expense before sending it', async () => {
    const fetchMock = mockFetch(routes())
    renderWithAuth('/expenses', ROUTES, ['expenses.view', 'expenses.manage'])
    const user = userEvent.setup()

    await user.click((await screen.findAllByRole('button', { name: /Add expense/ }))[0])
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Add expense' }))
    expect(await within(dialog).findByText('Choose a category.')).toBeInTheDocument()
    expect(within(dialog).getByText('Enter an amount.')).toBeInTheDocument()
    expect(within(dialog).getByText('Say what the money was for.')).toBeInTheDocument()
    expect(fetchMock.count('POST /expenses/')).toBe(0)
  })

  it('edits an expense and shows server field errors', async () => {
    const fetchMock = mockFetch(
      routes(page([expense()]), {
        'PATCH /expenses/e1/': [
          { status: 400, body: { amount: ['Ensure this value is greater than or equal to 0.01.'] } },
          { status: 200, body: expense({ amount: '45000.00' }) },
        ],
      }),
    )
    renderWithAuth('/expenses', ROUTES, ['expenses.view', 'expenses.manage'])
    const user = userEvent.setup()

    await user.click(within(await screen.findByRole('table', { name: 'expenses' })).getByText('October rent'))
    const dialog = screen.getByRole('dialog')
    const amount = within(dialog).getByLabelText('Amount (TZS)')
    await user.clear(amount)
    await user.type(amount, '45000')
    await user.click(within(dialog).getByRole('button', { name: 'Save' }))
    expect(await within(dialog).findByText('Ensure this value is greater than or equal to 0.01.')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const body = JSON.parse(String(fetchMock.calls.filter((c) => c.key === 'PATCH /expenses/e1/')[1].init.body))
    expect(body).toEqual({
      category: 'cat-rent',
      amount: '45000',
      expense_date: '2026-10-12',
      description: 'October rent',
      paid_to: 'Landlord',
    })
  })

  it('only offers delete with expenses.delete', async () => {
    mockFetch(routes())
    renderWithAuth('/expenses', ROUTES, ['expenses.view', 'expenses.manage'])
    const user = userEvent.setup()
    await user.click(within(await screen.findByRole('table', { name: 'expenses' })).getByText('October rent'))
    expect(within(screen.getByRole('dialog')).queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('deletes an expense after confirmation', async () => {
    const fetchMock = mockFetch(routes(page([expense()]), { 'DELETE /expenses/e1/': { status: 204 } }))
    renderWithAuth('/expenses', ROUTES, ['expenses.view', 'expenses.manage', 'expenses.delete'])
    const user = userEvent.setup()

    await user.click(within(await screen.findByRole('table', { name: 'expenses' })).getByText('October rent'))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }))
    await user.click(screen.getByRole('button', { name: 'Delete expense' }))
    await waitFor(() => expect(fetchMock.count('DELETE /expenses/e1/')).toBe(1))
  })
})
