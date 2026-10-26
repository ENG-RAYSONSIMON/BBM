import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { FormError } from '@/components/form-error'
import { AuthLayout } from '@/components/layout/auth-layout'
import { PasswordField } from '@/components/password-field'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-context'
import { applyServerErrors } from '@/lib/forms'
import { changePasswordSchema } from '@/lib/schemas'
import type { ChangePasswordValues } from '@/lib/schemas'

/**
 * Choose my own password. Someone on a temporary password from the owner is
 * sent here at first login and can't leave until it's done (but can log out).
 */
export function ChangePasswordPage() {
  const { me, changePassword, logout } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const firstLogin = me?.user.must_change_password ?? false

  const form = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { current_password: '', new_password: '', confirm_password: '' },
  })
  const { errors, isSubmitting } = form.formState

  async function onSubmit({ current_password, new_password }: ChangePasswordValues) {
    try {
      await changePassword({ current_password, new_password })
    } catch (error) {
      applyServerErrors(error, form.setError, ['current_password', 'new_password'])
      return
    }
    toast.success(t('account.passwordSaved'))
    navigate('/', { replace: true })
  }

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  const footer = firstLogin ? (
    <Button variant="link" className="h-auto p-0" onClick={handleLogout}>
      {t('nav.logout')}
    </Button>
  ) : (
    <Link to="/" className="text-foreground font-medium underline-offset-4 hover:underline">
      {t('common.goToDashboard')}
    </Link>
  )

  return (
    <AuthLayout
      title={firstLogin ? t('account.firstLoginTitle') : t('account.changePasswordTitle')}
      description={firstLogin ? t('account.firstLoginText', { business: me?.business.name ?? '' }) : undefined}
      footer={footer}
    >
      <form className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        <FormError message={errors.root?.server?.message} />
        <PasswordField
          label={firstLogin ? t('account.tempPassword') : t('account.currentPassword')}
          autoComplete="current-password"
          error={errors.current_password?.message}
          {...form.register('current_password')}
        />
        <PasswordField
          label={t('auth.newPassword')}
          autoComplete="new-password"
          hint={t('auth.passwordHint')}
          error={errors.new_password?.message}
          {...form.register('new_password')}
        />
        <PasswordField
          label={t('auth.confirmNewPassword')}
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
