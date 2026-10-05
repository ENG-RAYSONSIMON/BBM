import type { ReactNode } from 'react'

import { Brand } from './brand'
import { ThemeToggle } from '@/components/theme-toggle'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

/** Centered card used by the login, register and password pages. */
export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <main className="bg-muted/40 relative flex min-h-svh flex-col items-center justify-center gap-6 px-4 py-16">
      <div className="absolute top-3 right-3">
        <ThemeToggle />
      </div>
      <Brand />
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-xl">{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
      {footer && <div className="text-muted-foreground text-sm">{footer}</div>}
    </main>
  )
}
