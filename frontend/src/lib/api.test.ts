import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { mockFetch } from '@/test/fetch-mock'

// api.ts keeps tokens in module state, so load a fresh copy per test.
async function loadApi() {
  vi.resetModules()
  return import('./api')
}

describe('api client', () => {
  beforeEach(() => {
    localStorage.setItem('bbm.refresh', 'refresh-old')
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('refreshes once for concurrent 401s, then retries each request', async () => {
    const { api, tokenStore } = await loadApi()
    tokenStore.set({ access: 'expired', refresh: 'refresh-old' })

    const fetchMock = mockFetch({
      'GET /a/': (init) =>
        (init.headers as Record<string, string>).Authorization === 'Bearer access-new'
          ? { status: 200, body: { ok: 'a' } }
          : { status: 401, body: { detail: 'expired' } },
      'GET /b/': (init) =>
        (init.headers as Record<string, string>).Authorization === 'Bearer access-new'
          ? { status: 200, body: { ok: 'b' } }
          : { status: 401, body: { detail: 'expired' } },
      'POST /auth/refresh/': { status: 200, body: { access: 'access-new', refresh: 'refresh-new' } },
    })

    const results = await Promise.all([api('/a/'), api('/b/')])

    expect(results).toEqual([{ ok: 'a' }, { ok: 'b' }])
    expect(fetchMock.count('POST /auth/refresh/')).toBe(1)
    expect(localStorage.getItem('bbm.refresh')).toBe('refresh-new')
  })

  it('uses the stored refresh token on first load (no access token yet)', async () => {
    const { api } = await loadApi()
    const fetchMock = mockFetch({
      'POST /auth/refresh/': { status: 200, body: { access: 'access-new', refresh: 'refresh-new' } },
      'GET /auth/me/': { status: 200, body: { id: 1 } },
    })

    await expect(api('/auth/me/')).resolves.toEqual({ id: 1 })
    expect(fetchMock.calls.map((c) => c.key)).toEqual(['POST /auth/refresh/', 'GET /auth/me/'])
  })

  it('ends the session when the refresh token is rejected', async () => {
    const { api, ApiError, onAuthLost, tokenStore } = await loadApi()
    tokenStore.set({ access: 'expired', refresh: 'refresh-old' })
    const lost = vi.fn()
    onAuthLost(lost)
    mockFetch({
      'GET /a/': { status: 401, body: { detail: 'expired' } },
      'POST /auth/refresh/': { status: 401, body: { detail: 'blacklisted' } },
    })

    await expect(api('/a/')).rejects.toBeInstanceOf(ApiError)
    expect(lost).toHaveBeenCalledOnce()
    expect(localStorage.getItem('bbm.refresh')).toBeNull()
    expect(tokenStore.getAccess()).toBeNull()
  })

  it('keeps the session when refresh is throttled', async () => {
    const { api, onAuthLost, tokenStore } = await loadApi()
    tokenStore.set({ access: 'expired', refresh: 'refresh-old' })
    const lost = vi.fn()
    onAuthLost(lost)
    mockFetch({
      'GET /a/': { status: 401, body: { detail: 'expired' } },
      'POST /auth/refresh/': { status: 429, body: { detail: 'slow down' } },
    })

    await expect(api('/a/')).rejects.toMatchObject({ status: 401 })
    expect(lost).not.toHaveBeenCalled()
    expect(localStorage.getItem('bbm.refresh')).toBe('refresh-old')
  })

  it('exposes DRF field errors', async () => {
    const { api } = await loadApi()
    mockFetch({
      'POST /auth/register/': {
        status: 400,
        body: { email: ['A user with this email already exists.'] },
      },
    })

    const error = await api('/auth/register/', { method: 'POST', body: {}, auth: false }).catch(
      (e: unknown) => e,
    )
    expect((error as { fieldErrors: () => Record<string, string> }).fieldErrors()).toEqual({
      email: 'A user with this email already exists.',
    })
  })
})
