import { SearchIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

/** Search box that reports its value after typing pauses (300 ms). */
export function SearchInput({
  value,
  onChange,
  placeholder: placeholderProp,
  className,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
}) {
  const { t } = useTranslation()
  const placeholder = placeholderProp ?? t('common.search')
  const [draft, setDraft] = useState(value)
  const [lastValue, setLastValue] = useState(value)

  // Follow outside changes (e.g. back button) without an extra effect.
  if (value !== lastValue) {
    setLastValue(value)
    setDraft(value)
  }

  useEffect(() => {
    if (draft === value) return
    const timer = setTimeout(() => onChange(draft), 300)
    return () => clearTimeout(timer)
  }, [draft, value, onChange])

  return (
    <div className={cn('relative', className)}>
      <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
      <Input
        type="search"
        aria-label={placeholder}
        placeholder={placeholder}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        className="h-10 pl-9 md:h-9"
      />
    </div>
  )
}
