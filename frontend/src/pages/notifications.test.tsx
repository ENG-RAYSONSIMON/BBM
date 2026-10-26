import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { NotificationsPage } from './notifications'
import { NotificationBell } from '@/components/notification-bell'
import type { AppNotification } from '@/lib/types'
import { mockFetch } from '@/test/fetch-mock'
import { EMPTY_PAGE, page } from '@/test/fixtures'
import { renderWithAuth } from '@/test/render'

function notification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: 'n1',
    kind: 'LOW_STOCK',
    channel: 'IN_APP',
    params: { product: 'p1', name: 'Shea Butter', stock: 3, unit: 'pcs', threshold: 5 },
    target_type: 'product',
    target_id: 'p1',
    is_read: false,
    resolved_at: null,
    created_at: '2026-10-26T07:00:00Z',
    ...overrides,
  }
}

const EXPIRED = notification({
  id: 'n2',
  kind: 'EXPIRED',
  params: { product: 'p1', name: 'Shea Butter', batch_number: 'B1', expiry_date: '2026-10-24', days: 2, stock: 4 },
  is_read: true,
  resolved_at: '2026-10-26T08:00:00Z',
})

const ROUTES = { '/notifications': <NotificationsPage />, '/products/:id': <p>Product page</p> }

describe('NotificationsPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists alerts in words, with their state', async () => {
    mockFetch({ 'GET /notifications/': { status: 200, body: page([notification(), EXPIRED]) } })
    renderWithAuth('/notifications', ROUTES, [])

    const table = await screen.findByRole('table', { name: 'notifications' })
    expect(within(table).getByText('Shea Butter is running low: 3 pcs left.')).toBeInTheDocument()
    expect(within(table).getByText('Shea Butter, batch B1: expired 2 days ago (24 Oct 2026). 4 still in stock.')).toBeInTheDocument()
    expect(within(table).getByText('New')).toBeInTheDocument()
    expect(within(table).getByText('Sorted')).toBeInTheDocument()
  })

  it('marks an alert read and opens its product', async () => {
    const mock = mockFetch({
      'GET /notifications/': { status: 200, body: page([notification()]) },
      'POST /notifications/n1/read/': { status: 204 },
    })
    renderWithAuth('/notifications', ROUTES, [])
    const table = await screen.findByRole('table', { name: 'notifications' })
    await userEvent.click(within(table).getByText(/running low/))
    expect(await screen.findByText('Product page')).toBeInTheDocument()
    await waitFor(() => expect(mock.count('POST /notifications/n1/read/')).toBe(1))
  })

  it('marks everything read', async () => {
    const mock = mockFetch({
      'GET /notifications/': { status: 200, body: page([notification()]) },
      'POST /notifications/read-all/': { status: 204 },
    })
    renderWithAuth('/notifications', ROUTES, [])
    await screen.findByRole('table', { name: 'notifications' })
    await userEvent.click(screen.getByRole('button', { name: /Mark all read/ }))
    await waitFor(() => expect(mock.count('POST /notifications/read-all/')).toBe(1))
    await waitFor(() => expect(mock.count('GET /notifications/')).toBe(2))
  })

  it('shows the empty state', async () => {
    mockFetch({ 'GET /notifications/': { status: 200, body: EMPTY_PAGE } })
    renderWithAuth('/notifications', ROUTES, [])
    expect(await screen.findByText('No notifications yet')).toBeInTheDocument()
  })
})

describe('NotificationBell', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows how many alerts are new', async () => {
    mockFetch({ 'GET /notifications/unread-count/': { status: 200, body: { unread: 3 } } })
    renderWithAuth('/bell', { '/bell': <NotificationBell /> }, [])
    const link = await screen.findByRole('link', { name: 'Notifications: 3 new' })
    expect(link).toHaveAttribute('href', '/notifications')
    expect(within(link).getByText('3')).toBeInTheDocument()
  })

  it('shows no count when all is read', async () => {
    mockFetch({ 'GET /notifications/unread-count/': { status: 200, body: { unread: 0 } } })
    renderWithAuth('/bell', { '/bell': <NotificationBell /> }, [])
    expect(await screen.findByRole('link', { name: 'Notifications' })).toBeInTheDocument()
  })
})
