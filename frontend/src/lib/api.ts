/**
 * Fetch wrapper for the BBM API.
 *
 * Tokens: the access token lives only in memory; the refresh token is kept in
 * localStorage so a reload keeps the session. On a 401 the client rotates the
 * refresh token once (shared by concurrent requests) and retries the request.
 */

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1').replace(
  /\/$/,
  '',
)

const REFRESH_KEY = 'bbm.refresh'

export type ApiErrorData = Record<string, unknown> | null

export class ApiError extends Error {
  readonly status: number
  readonly data: ApiErrorData

  constructor(status: number, data: ApiErrorData) {
    super(errorMessage(status, data))
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }

  /** DRF field errors as {field: first message}. */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {}
    if (!this.data) return out
    for (const [key, value] of Object.entries(this.data)) {
      if (Array.isArray(value) && typeof value[0] === 'string') out[key] = value[0]
    }
    return out
  }
}

function errorMessage(status: number, data: ApiErrorData): string {
  if (status === 0) return 'Could not reach the server. Check your connection and try again.'
  if (status === 429) return 'Too many attempts. Please wait a minute and try again.'
  const detail = data?.detail
  if (typeof detail === 'string') return detail
  const nonField = data?.non_field_errors
  if (Array.isArray(nonField) && typeof nonField[0] === 'string') return nonField[0]
  if (status >= 500) return 'Something went wrong on our side. Please try again.'
  return 'Request failed.'
}

// ---- token store -----------------------------------------------------------

let accessToken: string | null = null

function readRefresh(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY)
  } catch {
    return null
  }
}

function writeRefresh(value: string | null) {
  try {
    if (value === null) localStorage.removeItem(REFRESH_KEY)
    else localStorage.setItem(REFRESH_KEY, value)
  } catch {
    // Storage unavailable (private mode, blocked): the session lasts until reload.
  }
}

export const tokenStore = {
  REFRESH_KEY,
  getAccess: () => accessToken,
  getRefresh: readRefresh,
  set(tokens: { access: string; refresh: string }) {
    accessToken = tokens.access
    writeRefresh(tokens.refresh)
  },
  clear() {
    accessToken = null
    writeRefresh(null)
  },
}

let authLostHandler: (() => void) | null = null

/** Called when the session can't be recovered (refresh token rejected). */
export function onAuthLost(handler: (() => void) | null) {
  authLostHandler = handler
}

// ---- refresh ----------------------------------------------------------------

let refreshing: Promise<boolean> | null = null

/** Rotate the refresh token. Concurrent callers share one request. */
export function refreshTokens(): Promise<boolean> {
  refreshing ??= doRefresh().finally(() => {
    refreshing = null
  })
  return refreshing
}

async function doRefresh(retried = false): Promise<boolean> {
  const refresh = readRefresh()
  if (!refresh) return false

  let res: Response
  try {
    res = await fetch(`${API_URL}/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
  } catch {
    return false // offline: keep the refresh token for a later attempt
  }

  if (res.ok) {
    tokenStore.set(await res.json())
    return true
  }
  if (res.status === 401) {
    // Another tab may have rotated the token in the meantime; use the new one.
    if (!retried && readRefresh() !== refresh) return doRefresh(true)
    tokenStore.clear()
    authLostHandler?.()
  }
  return false // 429 / 5xx: transient, keep the session
}

// ---- requests ---------------------------------------------------------------

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  /** JSON-encoded, except FormData which is sent as multipart. */
  body?: unknown
  /** Send the bearer token and refresh on 401. Default true. */
  auth?: boolean
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = true } = options

  if (auth && !accessToken && readRefresh()) await refreshTokens()

  let res = await send(path, method, body, auth)
  if (res.status === 401 && auth && readRefresh()) {
    if (await refreshTokens()) res = await send(path, method, body, auth)
  }

  const data = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data)
  return data as T
}

async function send(path: string, method: string, body: unknown, auth: boolean) {
  const isForm = body instanceof FormData
  const headers: Record<string, string> = { Accept: 'application/json' }
  // For FormData the browser sets the multipart Content-Type and boundary.
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`
  try {
    return await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, null)
  }
}
