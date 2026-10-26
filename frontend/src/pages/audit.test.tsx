import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuditPage } from './audit'
import type { AuditLogEntry } from '@/lib/types'
import { mockFetch } from '@/test/fetch-mock'
import { EMPTY_PAGE, page } from '@/test/fixtures'
import { renderWithAuth } from '@/test/render'

function entry(overrides: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: 'a1',
    action: 'EXPENSE_CHANGE',
    actor: 'u1',
    actor_name: 'Asha Juma',
    target_type: 'expense',
    target_id: 'e1',
    target_label: 'October rent',
    changes: { amount: ['50000.00', '55000.00'] },
    ip_address: '127.0.0.1',
    created_at: '2026-10-20T09:30:00Z',
    ...overrides,
  }
}

describe('AuditPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists entries with action, actor, target and changes', async () => {
    mockFetch({
      'GET /audit-logs/': {
        status: 200,
        body: page([
          entry(),
          entry({ id: 'a2', action: 'SALE_VOID', actor_name: '', target_type: 'sale', target_label: 'R-000004',
            changes: { reason: 'Wrong item' } }),
        ]),
      },
    })
    renderWithAuth('/audit', { '/audit': <AuditPage /> }, ['audit.view'])

    const table = await screen.findByRole('table', { name: 'audit log' })
    expect(within(table).getByText('Expense changed')).toBeInTheDocument()
    expect(within(table).getByText('Asha Juma')).toBeInTheDocument()
    expect(within(table).getByText('Expense: October rent')).toBeInTheDocument()
    expect(within(table).getByText('Amount: 50000.00 → 55000.00')).toBeInTheDocument()
    expect(within(table).getByText('Sale voided')).toBeInTheDocument()
    expect(within(table).getByText('System')).toBeInTheDocument()
    expect(within(table).getByText('Reason: Wrong item')).toBeInTheDocument()
  })

  it('shows the empty state', async () => {
    mockFetch({ 'GET /audit-logs/': { status: 200, body: EMPTY_PAGE } })
    renderWithAuth('/audit', { '/audit': <AuditPage /> }, ['audit.view'])
    expect(await screen.findByText('Nothing logged yet')).toBeInTheDocument()
  })

  it('shows an error with a retry button', async () => {
    mockFetch({ 'GET /audit-logs/': { status: 403, body: { detail: 'You do not have permission to perform this action.' } } })
    renderWithAuth('/audit', { '/audit': <AuditPage /> }, [])
    expect(await screen.findByText('You do not have permission to perform this action.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
