import { Loader2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'

export function FullPageLoading() {
  return (
    <div className="flex min-h-svh items-center justify-center" role="status" aria-live="polite">
      <Loader2Icon className="text-muted-foreground size-6 animate-spin" />
      <span className="sr-only">Loading…</span>
    </div>
  )
}

export function FullPageError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-4 px-4 text-center">
      <p className="text-muted-foreground max-w-sm">{message}</p>
      <Button onClick={onRetry}>Try again</Button>
    </div>
  )
}
