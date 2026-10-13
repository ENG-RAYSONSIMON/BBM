import { zodResolver } from '@hookform/resolvers/zod'
import { MailCheckIcon } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'

import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { AuthLayout } from '@/components/layout/auth-layout'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { applyServerErrors } from '@/lib/forms'
import { forgotPasswordSchema } from '@/lib/schemas'
import type { ForgotPasswordValues } from '@/lib/schemas'

function BackToLogin() {
  const { t } = useTranslation()
  return (
    <Link to="/login" className="text-foreground font-medium underline-offset-4 hover:underline">
      {t('auth.backToLogin')}
    </Link>
  )
}

export function ForgotPasswordPage() {
  const { t } = useTranslation()
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
      <AuthLayout title={t('auth.checkEmail')} footer={<BackToLogin />}>
        <div className="flex gap-3">
          <MailCheckIcon className="text-muted-foreground mt-0.5 size-5 shrink-0" />
          <p className="text-sm">{sentMessage}</p>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title={t('auth.forgotTitle')}
      description={t('auth.forgotText')}
      footer={<BackToLogin />}
    >
      <form className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        <FormError message={errors.root?.server?.message} />
        <FormField
          label={t('common.email')}
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...form.register('email')}
        />
        <Button type="submit" size="lg" disabled={isSubmitting}>
          {isSubmitting ? t('auth.sending') : t('auth.sendLink')}
        </Button>
      </form>
    </AuthLayout>
  )
}
