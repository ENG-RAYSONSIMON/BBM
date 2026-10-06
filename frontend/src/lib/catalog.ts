import { useQuery } from '@tanstack/react-query'

import { api } from './api'
import type { Paginated, Ref } from './types'

export type RefKind = 'categories' | 'brands' | 'suppliers'

/** Every category / brand / supplier, for dropdowns (API max page size). */
export function useRefOptions(kind: RefKind, enabled = true) {
  return useQuery({
    queryKey: [kind, 'options'],
    queryFn: () => api<Paginated<Ref>>(`/${kind}/?page_size=100&ordering=name`),
    select: (page) => page.results,
    enabled,
    staleTime: 60_000,
  })
}
