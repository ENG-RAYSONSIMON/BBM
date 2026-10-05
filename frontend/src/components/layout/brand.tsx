import { SparklesIcon } from 'lucide-react'

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2 font-semibold">
      <span className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-lg">
        <SparklesIcon className="size-4" />
      </span>
      {!compact && <span>Beauty Business Manager</span>}
    </div>
  )
}
