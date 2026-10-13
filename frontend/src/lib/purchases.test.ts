import { describe, expect, it } from 'vitest'

import { periodRange } from './dates'
import { lineError, purchaseTotal } from './purchases'
import type { PurchaseLine } from './purchases'

function line(overrides: Partial<PurchaseLine> = {}): PurchaseLine {
  return {
    key: 'l1',
    product: 'p1',
    productName: 'Shea Butter',
    tracksExpiry: true,
    quantity: '10',
    unitCost: '7500',
    batchNumber: 'SB-01',
    expiryDate: '2027-06-30',
    ...overrides,
  }
}

describe('purchase lines', () => {
  it('totals quantity × unit cost in cents, skipping incomplete lines', () => {
    expect(purchaseTotal([line(), line({ quantity: '3', unitCost: '1200.50' })])).toBe(7_500_000 + 360_150)
    expect(purchaseTotal([line({ quantity: '' }), line({ unitCost: 'abc' })])).toBe(0)
  })

  it('flags what the server would refuse', () => {
    expect(lineError(line())).toBeUndefined()
    expect(lineError(line({ quantity: '0' }))).toBe('errors.lineQuantity')
    expect(lineError(line({ quantity: '1.5' }))).toBe('errors.lineQuantity')
    expect(lineError(line({ unitCost: '' }))).toBe('errors.lineUnitCost')
    expect(lineError(line({ batchNumber: ' ' }))).toBe('errors.lineBatch')
    expect(lineError(line({ tracksExpiry: false, batchNumber: '' }))).toBeUndefined()
  })
})

describe('periodRange', () => {
  const now = new Date(2026, 9, 13) // 13 Oct 2026, local time

  it("leaves today to the server's clock", () => {
    expect(periodRange('today', now)).toEqual({})
  })

  it('covers the last 7 days and the month so far', () => {
    expect(periodRange('week', now)).toEqual({ date_from: '2026-10-07', date_to: '2026-10-13' })
    expect(periodRange('month', now)).toEqual({ date_from: '2026-10-01', date_to: '2026-10-13' })
  })
})
