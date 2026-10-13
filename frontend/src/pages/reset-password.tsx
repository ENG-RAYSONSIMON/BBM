import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { AuthLayout } from '@/components/layout/auth-layout'
import { Button } from '@/components/ui/button'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { applyServerErrors } from '@/lib/forms'
import { readTokenFromHash } from '@/lib/reset-token'
import { resetPasswordSchema } from '@/lib/schemas'
import type { ResetPasswordValues } from '@/lib/schemas'

export function ResetPasswordPage() {
  const [token] = useState(() => readTokenFromHash(window.location.hash))

  // Drop the token from the address bar (and so from history) once read.
  useEffect(() => {
    if (window.location.hash) {
      window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search)
    }
  }, [])
  const { status, logout } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()

  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { new_password: '', confirm_password: '' },
  })
  const { errors, isSubmitting } = form.formState

  async function onSubmit({ new_password }: ResetPasswordValues) {
    try {
      await api('/auth/password-reset/confirm/', {
        method: 'POST',
        body: { token, new_password },
        auth: false,
      })
      // The reset ended every session on the server; end this one too.
      if (status === 'authenticated') await logout()
      toast.success(t('auth.passwordChanged'))
      navigate('/login', { replace: true })
    } catch (error) {
      const tokenError = error instanceof ApiError ? error.fieldErrors().token : undefined
      if (tokenError) form.setError('root.server', { message: tokenError })
      else applyServerErrors(error, form.setError, ['new_password'])
    }
  }

  const requestAgain = (
    <Link to="/forgot-password" className="text-foreground font-medium underline-offset-4 hover:underline">
      {t('auth.requestNewLink')}
    </Link>
  )

  if (!token) {
    return (
      <AuthLayout title={t('auth.linkMissing')} footer={requestAgain}>
        <p className="text-sm">{t('auth.linkMissingText')}</p>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title={t('auth.newPasswordTitle')} footer={requestAgain}>
      <form className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        <FormError message={errors.root?.server?.message} />
        <FormField
          label={t('auth.newPassword')}
          type="password"
          autoComplete="new-password"
          hint={t('auth.passwordHint')}
          error={errors.new_password?.message}
          {...form.register('new_password')}
        />
        <FormField
          label={t('auth.confirmNewPassword')}
          type="password"
          autoComplete="new-password"
          error={errors.confirm_password?.message}
          {...form.register('confirm_password')}
        />
        <Button type="submit" size="lg" disabled={isSubmitting}>
          {isSubmitting ? t('common.saving') : t('auth.setNewPassword')}
        </Button>
      </form>
    </AuthLayout>
  )
}
