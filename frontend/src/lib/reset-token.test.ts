import { describe, expect, it } from 'vitest'

import { readTokenFromHash } from './reset-token'

describe('readTokenFromHash', () => {
  it('reads the token from the link fragment', () => {
    expect(readTokenFromHash('#token=abc-DEF_123')).toBe('abc-DEF_123')
  })

  it('returns null when there is no token', () => {
    expect(readTokenFromHash('')).toBeNull()
    expect(readTokenFromHash('#other=1')).toBeNull()
  })
})
