import { useId } from 'react'
import type { ComponentProps, ReactNode } from 'react'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useTranslateMessage } from '@/i18n'
import { cn } from '@/lib/utils'

type FormFieldProps = ComponentProps<typeof Input> & {
  label: string
  error?: string
  hint?: string
  /** A small button inside the right end of the box (e.g. show password). */
  trailing?: ReactNode
}

/** Label + input + error/hint, wired up for screen readers. */
export function FormField({ label, error, hint, trailing, id, className, ...props }: FormFieldProps) {
  const fallbackId = useId()
  const translate = useTranslateMessage()
  const inputId = id ?? fallbackId
  const messageId = `${inputId}-message`
  // Errors may be dictionary keys (client checks) or server text.
  const message = translate(error) ?? hint

  return (
    <div className="grid gap-1.5">
      <Label htmlFor={inputId}>{label}</Label>
      <div className="relative">
        <Input
          id={inputId}
          // Taller on touch screens.
          className={cn('h-10 md:h-9', trailing && 'pr-11', className)}
          aria-invalid={error ? true : undefined}
          aria-describedby={message ? messageId : undefined}
          {...props}
        />
        {trailing && <div className="absolute inset-y-0 right-0 flex items-center pr-1">{trailing}</div>}
      </div>
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
