import { useId } from 'react'
import type { ComponentProps } from 'react'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

type FormFieldProps = ComponentProps<typeof Input> & {
  label: string
  error?: string
  hint?: string
}

/** Label + input + error/hint, wired up for screen readers. */
export function FormField({ label, error, hint, id, className, ...props }: FormFieldProps) {
  const fallbackId = useId()
  const inputId = id ?? fallbackId
  const messageId = `${inputId}-message`
  const message = error ?? hint

  return (
    <div className="grid gap-1.5">
      <Label htmlFor={inputId}>{label}</Label>
      <Input
        id={inputId}
        // Taller on touch screens.
        className={cn('h-10 md:h-9', className)}
        aria-invalid={error ? true : undefined}
        aria-describedby={message ? messageId : undefined}
        {...props}
      />
      {message && (
        <p
          id={messageId}
          className={error ? 'text-destructive text-sm' : 'text-muted-foreground text-sm'}
        >
          {message}
        </p>
      )}
    </div>
  )
}
