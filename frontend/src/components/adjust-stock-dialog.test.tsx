import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AdjustStockDialog } from './adjust-stock-dialog'
import { mockFetch } from '@/test/fetch-mock'
import { batch, product } from '@/test/fixtures'

function renderDialog() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AdjustStockDialog product={product()} batches={[batch()]} open onOpenChange={() => {}} />
    </QueryClientProvider>,
  )
}

async function choose(user: ReturnType<typeof userEvent.setup>, label: string, option: string | RegExp) {
  await user.click(screen.getByRole('combobox', { name: label }))
  await user.click(await screen.findByRole('option', { name: option }))
}

describe('AdjustStockDialog', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends a negative quantity for damage and shows the server stock error', async () => {
    const fetchMock = mockFetch({
      'POST /stock-movements/': { status: 400, body: { quantity: ['Only 3 in stock in this batch.'] } },
    })
    renderDialog()
    const user = userEvent.setup()
    const dialog = screen.getByRole('dialog')

    await choose(user, 'What happened?', 'Damaged')
    await choose(user, 'Batch', /L-001/)
    await user.type(within(dialog).getByLabelText('Quantity to remove'), '5')
    await user.type(within(dialog).getByLabelText('Note'), 'Dropped')
    await user.click(within(dialog).getByRole('button', { name: 'Remove stock' }))

    expect(await screen.findByText('Only 3 in stock in this batch.')).toBeInTheDocument()
    const body = JSON.parse(String(fetchMock.calls[0].init.body))
    expect(body).toMatchObject({ movement_type: 'DAMAGE', quantity: -5, batch: 'b1', reason: 'Dropped' })
  })

  it('asks for batch number and expiry when receiving into a new batch', async () => {
    const fetchMock = mockFetch({})
    renderDialog()
    const user = userEvent.setup()
    const dialog = screen.getByRole('dialog')

    await user.type(within(dialog).getByLabelText('Quantity to add'), '10')
    await user.type(within(dialog).getByLabelText('Note'), 'Delivery')
    await user.click(within(dialog).getByRole('button', { name: 'Add stock' }))

    expect(await screen.findByText('Enter the batch or lot number.')).toBeInTheDocument()
    expect(screen.getByText('Enter the expiry date.')).toBeInTheDocument()
    expect(fetchMock.calls).toHaveLength(0)
  })
})
