import { ChevronLeftIcon, ChevronRightIcon, InboxIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { FormError } from '@/components/form-error'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { Paginated } from '@/lib/types'
import { cn } from '@/lib/utils'

export const PAGE_SIZE = 25

export type Column<T> = {
  header: string
  cell: (item: T) => ReactNode
  className?: string
}

type DataListProps<T> = {
  query: {
    data: Paginated<T> | undefined
    isPending: boolean
    isError: boolean
    error: Error | null
    refetch: () => unknown
  }
  columns: Column<T>[]
  /** Mobile layout for one item. */
  card: (item: T) => ReactNode
  rowKey: (item: T) => string
  onRowClick?: (item: T) => void
  page: number
  onPageChange: (page: number) => void
  empty: { title: string; description?: string; action?: ReactNode }
  label: string
}

/**
 * NFR-10 list: loading, empty and error states plus pagination. A table from
 * md up, cards below.
 */
export function DataList<T>({
  query,
  columns,
  card,
  rowKey,
  onRowClick,
  page,
  onPageChange,
  empty,
  label,
}: DataListProps<T>) {
  if (query.isPending) {
    return (
      <div className="grid gap-2" role="status" aria-label={`Loading ${label}`}>
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-14" />
        ))}
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="grid justify-items-start gap-3">
        <FormError message={query.error?.message ?? `Could not load ${label}.`} />
        <Button variant="outline" size="lg" onClick={() => query.refetch()}>
          Try again
        </Button>
      </div>
    )
  }

  const { results, count } = query.data!
  if (count === 0) {
    return (
      <Card className="flex flex-col items-center gap-2 px-6 py-12 text-center">
        <InboxIcon className="text-muted-foreground size-8" />
        <p className="font-medium">{empty.title}</p>
        {empty.description && <p className="text-muted-foreground max-w-sm text-sm">{empty.description}</p>}
        {empty.action && <div className="mt-2">{empty.action}</div>}
      </Card>
    )
  }

  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE))

  return (
    <div className="grid gap-3">
      <Card className="hidden overflow-hidden py-0 md:block">
        <Table aria-label={label}>
          <TableHeader>
            <TableRow>
              {columns.map((column) => (
                <TableHead key={column.header} className={column.className}>
                  {column.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.map((item) => (
              <TableRow
                key={rowKey(item)}
                className={cn(onRowClick && 'cursor-pointer')}
                onClick={onRowClick ? () => onRowClick(item) : undefined}
              >
                {columns.map((column) => (
                  <TableCell key={column.header} className={column.className}>
                    {column.cell(item)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <ul className="grid gap-2 md:hidden" aria-label={label}>
        {results.map((item) => (
          <li key={rowKey(item)}>{card(item)}</li>
        ))}
      </ul>

      {pages > 1 && (
        <nav className="flex items-center justify-between gap-2" aria-label="Pagination">
          <p className="text-muted-foreground text-sm">
            Page {page} of {pages} · {count} total
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="icon-lg"
              aria-label="Previous page"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              <ChevronLeftIcon />
            </Button>
            <Button
              variant="outline"
              size="icon-lg"
              aria-label="Next page"
              disabled={page >= pages}
              onClick={() => onPageChange(page + 1)}
            >
              <ChevronRightIcon />
            </Button>
          </div>
        </nav>
      )}
    </div>
  )
}
