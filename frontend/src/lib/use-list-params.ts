import { useCallback } from 'react'
import { useSearchParams } from 'react-router'

/**
 * List state (page, search, filters) kept in the URL, so reload, back and
 * shared links keep it. Changing anything but the page resets to page 1.
 */
export function useListParams() {
  const [params, setParams] = useSearchParams()

  const get = useCallback((key: string) => params.get(key) ?? '', [params])

  /** Set several params in one navigation. */
  const setMany = useCallback(
    (values: Record<string, string>) => {
      const keys = Object.keys(values)
      const pageOnly = keys.length === 1 && keys[0] === 'page'
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [key, value] of Object.entries(values)) {
            if (value) next.set(key, value)
            else next.delete(key)
          }
          if (!pageOnly) next.delete('page')
          return next
        },
        { replace: !pageOnly },
      )
    },
    [setParams],
  )
  const set = useCallback((key: string, value: string) => setMany({ [key]: value }), [setMany])

  const page = Math.max(1, Number(params.get('page')) || 1)
  const setPage = useCallback((value: number) => set('page', value > 1 ? String(value) : ''), [set])
  const search = get('search')
  const setSearch = useCallback((value: string) => set('search', value), [set])

  return { params, get, set, setMany, page, setPage, search, setSearch }
}

/** Query string from an object, skipping empty values. */
export function toQuery(values: Record<string, string | number | undefined | null>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  }
  const text = query.toString()
  return text ? `?${text}` : ''
}
