import { vi } from 'vitest'

type Reply = { status: number; body?: unknown }
type Handler = Reply | ((init: RequestInit) => Reply)

/**
 * Stub global fetch. `routes` maps "METHOD /path/" (relative to the API URL)
 * to a reply, or to a list of replies used in order (the last one repeats).
 */
export function mockFetch(routes: Record<string, Handler | Handler[]>) {
  const calls: { key: string; init: RequestInit }[] = []
  const used: Record<string, number> = {}

  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input))
    const path = url.pathname.replace(/^\/api\/v1/, '')
    const key = `${init.method ?? 'GET'} ${path}`
    calls.push({ key, init })

    const route = routes[key]
    if (!route) throw new Error(`Unexpected request: ${key}`)
    const list = Array.isArray(route) ? route : [route]
    const index = Math.min(used[key] ?? 0, list.length - 1)
    used[key] = (used[key] ?? 0) + 1
    const handler = list[index]
    const reply = typeof handler === 'function' ? handler(init) : handler

    return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), {
      status: reply.status,
      headers: { 'Content-Type': 'application/json' },
    })
  })

  vi.stubGlobal('fetch', fn)
  return {
    calls,
    count: (key: string) => calls.filter((c) => c.key === key).length,
  }
}

export const ME = {
  user: { id: 'u1', email: 'owner@example.com', first_name: 'Amina', last_name: '', phone: '' },
  business: {
    id: 'b1',
    name: 'Glow Cosmetics',
    tin: '',
    phone: '',
    email: '',
    address: '',
    currency: 'TZS',
  },
  role: 'Owner',
  permissions: ['settings.manage', 'settings.view'],
}

export const AUTH_PAYLOAD = {
  access: 'access-1',
  refresh: 'refresh-1',
  user: ME.user,
  business: ME.business,
  role: 'Owner',
}
