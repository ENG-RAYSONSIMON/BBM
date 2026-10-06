import { describe, expect, it } from 'vitest'

import { formatDate, formatQuantity, formatTZS } from './format'

describe('formatTZS', () => {
  it('formats decimal strings as whole shillings', () => {
    expect(formatTZS('15000.00')).toMatch(/15,000/)
    expect(formatTZS('15000.00')).toMatch(/TSh|TZS/)
    expect(formatTZS(1234567)).toMatch(/1,234,567/)
  })

  it('shows a dash for non-numbers', () => {
    expect(formatTZS('abc')).toBe('—')
  })
})

describe('formatDate', () => {
  it('treats API dates as calendar dates', () => {
    expect(formatDate('2026-01-01')).toBe('1 Jan 2026')
    expect(formatDate(null)).toBe('—')
  })
})

describe('formatQuantity', () => {
  it('signs quantities', () => {
    expect(formatQuantity(5)).toBe('+5')
    expect(formatQuantity(-3)).toBe('−3')
  })
})
