import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProductFormPage } from './product-form'
import { mockFetch } from '@/test/fetch-mock'
import { product, REF_ROUTES } from '@/test/fixtures'
import { renderWithAuth } from '@/test/render'

const PERMS = ['catalog.view', 'catalog.manage']

function renderForm() {
  return renderWithAuth(
    '/products/new',
    { '/products/new': <ProductFormPage />, '/products/:id': <p>Detail page</p> },
    PERMS,
  )
}

describe('ProductFormPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('validates required fields before calling the server', async () => {
    const fetchMock = mockFetch(REF_ROUTES)
    renderForm()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Add product' }))

    expect(await screen.findByText('Enter the product name.')).toBeInTheDocument()
    expect(screen.getAllByText('Enter an amount.')).toHaveLength(2)
    expect(fetchMock.count('POST /products/')).toBe(0)
  })

  it('shows server field errors and saves on success', async () => {
    const fetchMock = mockFetch({
      ...REF_ROUTES,
      'POST /products/': [
        { status: 400, body: { sku: ['A product with this SKU already exists.'] } },
        { status: 201, body: product({ id: 'new-id' }) },
      ],
    })
    renderForm()
    const user = userEvent.setup()

    await user.type(screen.getByLabelText('Name'), 'Shea Butter')
    await user.type(screen.getByLabelText('SKU (optional)'), 'SHEA-1')
    await user.type(screen.getByLabelText('Selling price'), '15000')
    await user.type(screen.getByLabelText('Cost (buying) price'), '9000')
    await user.click(screen.getByRole('button', { name: 'Add product' }))

    expect(await screen.findByText('A product with this SKU already exists.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add product' }))
    expect(await screen.findByText('Detail page')).toBeInTheDocument()
    const body = JSON.parse(String(fetchMock.calls.at(-1)!.init.body))
    expect(body).toMatchObject({ name: 'Shea Butter', selling_price: '15000', reorder_level: null, category: null })
  })

  it('rejects a non-image file before upload', async () => {
    mockFetch(REF_ROUTES)
    renderForm()
    const user = userEvent.setup({ applyAccept: false })

    await user.upload(screen.getByLabelText('Product image'), new File(['hi'], 'notes.txt', { type: 'text/plain' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Use a JPEG, PNG or WebP image.')
  })
})
