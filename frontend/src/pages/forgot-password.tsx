import { zodResolver } from '@hookform/resolvers/zod'
import { MailCheckIcon } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'

import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { AuthLayout } from '@/components/layout/auth-layout'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { applyServerErrors } from '@/lib/forms'
import { forgotPasswordSchema } from '@/lib/schemas'
import type { ForgotPasswordValues } from '@/lib/schemas'

const backToLogin = (
  <Link to="/login" className="text-foreground font-medium underline-offset-4 hover:underline">
    Back to log in
  </Link>
)

export function ForgotPasswordPage() {
  // The server answers the same way whether or not the account exists.
  const [sentMessage, setSentMessage] = useState<string | null>(null)

  const form = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: '' },
  })
  const { errors, isSubmitting } = form.formState

  async function onSubmit(values: ForgotPasswordValues) {
    try {
      const { detail } = await api<{ detail: string }>('/auth/password-reset/', {
        method: 'POST',
        body: values,
        auth: false,
      })
      setSentMessage(detail)
    } catch (error) {
      applyServerErrors(error, form.setError, ['email'])
    }
  }

  if (sentMessage) {
    return (
      <AuthLayout title="Check your email" footer={backToLogin}>
        <div className="flex gap-3">
          <MailCheckIcon className="text-muted-foreground mt-0.5 size-5 shrink-0" />
          <p className="text-sm">{sentMessage}</p>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Reset your password"
      description="Enter your account email and we'll send you a reset link."
      footer={backToLogin}
    >
      <form className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        <FormError message={errors.root?.server?.message} />
        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...form.register('email')}
        />
        <Button type="submit" size="lg" disabled={isSubmitting}>
          {isSubmitting ? 'Sending…' : 'Send reset link'}
        </Button>
      </form>
    </AuthLayout>
  )
}
