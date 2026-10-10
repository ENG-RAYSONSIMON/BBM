import { describe, expect, it } from 'vitest'

import { cartTotals, fromCents, tender, toCents } from './money'

describe('money', () => {
  it('parses amounts to cents and back', () => {
    expect(toCents('12000')).toBe(1_200_000)
    expect(toCents('12,000.5')).toBe(1_200_050)
    expect(toCents('')).toBe(0)
    expect(toCents('12.345')).toBeNull()
    expect(toCents('-5')).toBeNull()
    expect(fromCents(1_200_050)).toBe('12000.50')
  })

  it('adds up lines and discounts without float noise', () => {
    const totals = cartTotals([
      { unitPrice: '0.10', quantity: 3, discount: '' },
      { unitPrice: '15000.00', quantity: 2, discount: '1000' },
    ])
    expect(totals).toEqual({ subtotal: 3_000_030, discount: 100_000, total: 2_900_030, lineErrors: {} })
  })

  it('flags a discount larger than its line', () => {
    const totals = cartTotals([{ unitPrice: '100.00', quantity: 1, discount: '101' }])
    expect(totals.lineErrors[0]).toBe('The discount is more than the line.')
    expect(totals.total).toBe(10_000)
  })

  it('splits cash into paid, change and balance', () => {
    expect(tender(2_300_000, 2_500_000)).toEqual({ paid: 2_300_000, change: 200_000, balance: 0 })
    expect(tender(2_300_000, 500_000)).toEqual({ paid: 500_000, change: 0, balance: 1_800_000 })
    expect(tender(2_300_000, 0)).toEqual({ paid: 0, change: 0, balance: 2_300_000 })
  })
})
