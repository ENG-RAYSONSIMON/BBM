import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { Ref } from '@/lib/types'

// Radix Select can't use '' as an item value.
const NONE = '__none__'

/** Dropdown for an optional reference (category, brand, supplier, filter). */
export function RefSelect({
  label,
  value,
  onChange,
  options,
  noneLabel = 'None',
  disabled,
  hideLabel = false,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: Ref[] | undefined
  noneLabel?: string
  disabled?: boolean
  hideLabel?: boolean
}) {
  return (
    <div className="grid gap-1.5">
      <Label className={hideLabel ? 'sr-only' : undefined}>{label}</Label>
      <Select
        value={value || NONE}
        onValueChange={(next) => onChange(next === NONE ? '' : next)}
        disabled={disabled}
      >
        <SelectTrigger aria-label={label} className="w-full data-[size=default]:h-10 md:data-[size=default]:h-9">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>{noneLabel}</SelectItem>
          {options?.map((option) => (
            <SelectItem key={option.id} value={option.id}>
              {option.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
