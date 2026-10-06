import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProductsPage } from './products'
import { mockFetch } from '@/test/fetch-mock'
import { EMPTY_PAGE, page, product, REF_ROUTES } from '@/test/fixtures'
import { renderWithAuth } from '@/test/render'

const VIEW = ['catalog.view']
const MANAGE = ['catalog.view', 'catalog.manage']

describe('ProductsPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows a loading state, then products with stock', async () => {
    mockFetch({ ...REF_ROUTES, 'GET /products/': { status: 200, body: page([product()]) } })
    renderWithAuth('/products', { '/products': <ProductsPage /> }, VIEW)

    expect(screen.getByRole('status', { name: 'Loading products' })).toBeInTheDocument()
    expect((await screen.findAllByText('Shea Butter')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Low stock').length).toBeGreaterThan(0)
  })

  it('offers to add the first product when the catalog is empty', async () => {
    mockFetch({ ...REF_ROUTES, 'GET /products/': { status: 200, body: EMPTY_PAGE } })
    renderWithAuth('/products', { '/products': <ProductsPage /> }, MANAGE)

    expect(await screen.findByText('No products yet')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /add product/i }).length).toBeGreaterThan(0)
  })

  it('hides Add product without catalog.manage', async () => {
    mockFetch({ ...REF_ROUTES, 'GET /products/': { status: 200, body: EMPTY_PAGE } })
    renderWithAuth('/products', { '/products': <ProductsPage /> }, VIEW)

    expect(await screen.findByText('No products yet')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /add product/i })).not.toBeInTheDocument()
  })

  it('shows an error with a retry button', async () => {
    mockFetch({ ...REF_ROUTES, 'GET /products/': { status: 500, body: {} } })
    renderWithAuth('/products', { '/products': <ProductsPage /> }, VIEW)

    expect(await screen.findByRole('alert')).toHaveTextContent(/went wrong/i)
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
