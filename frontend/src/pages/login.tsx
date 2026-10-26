import { zodResolver } from '@hookform/resolvers/zod'
import { BuildingIcon } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useLocation, useNavigate } from 'react-router'
import type { Location } from 'react-router'
import { useTranslation } from 'react-i18next'

import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { AuthLayout } from '@/components/layout/auth-layout'
import { PasswordField } from '@/components/password-field'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { applyServerErrors } from '@/lib/forms'
import { loginSchema } from '@/lib/schemas'
import type { LoginValues } from '@/lib/schemas'
import type { BusinessChoice } from '@/lib/types'

export function LoginPage() {
  const { login } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: Location } | null)?.from?.pathname ?? '/'

  // Set when the account belongs to several businesses (400 with `businesses`).
  const [businesses, setBusinesses] = useState<BusinessChoice[] | null>(null)

  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  })
  const { errors, isSubmitting } = form.formState

  async function submit(values: LoginValues, businessId?: string) {
    try {
      await login({ ...values, business_id: businessId })
      navigate(from, { replace: true })
    } catch (error) {
      const choices = error instanceof ApiError ? error.data?.businesses : undefined
      if (Array.isArray(choices) && !businessId) {
        setBusinesses(choices as BusinessChoice[])
        return
      }
      if (error instanceof ApiError && error.status === 401) {
        form.setError('root.server', { message: 'auth.wrongLogin' })
        return
      }
      applyServerErrors(error, form.setError, ['email', 'password'])
    }
  }

  if (businesses) {
    return (
      <AuthLayout title={t('auth.chooseBusiness')} description={t('auth.manyBusinesses')}>
        <div className="grid gap-2">
          <FormError message={errors.root?.server?.message} />
          {businesses.map((business) => (
            <Button
              key={business.id}
              variant="outline"
              size="lg"
              className="justify-start"
              disabled={isSubmitting}
              onClick={form.handleSubmit((values) => submit(values, business.id))}
            >
              <BuildingIcon />
              {business.name}
            </Button>
          ))}
          <Button variant="link" onClick={() => setBusinesses(null)}>
            {t('auth.differentAccount')}
          </Button>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title={t('auth.login')}
      description={t('auth.loginWelcome')}
      footer={
        <>
          {t('auth.newToBbm')}{' '}
          <Link to="/register" className="text-foreground font-medium underline-offset-4 hover:underline">
            {t('auth.createAccount')}
          </Link>
        </>
      }
    >
      <form className="grid gap-4" noValidate onSubmit={form.handleSubmit((values) => submit(values))}>
        <FormError message={errors.root?.server?.message} />
        <FormField
          label={t('common.email')}
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...form.register('email')}
        />
        <div className="grid gap-1.5">
          <PasswordField
            label={t('auth.password')}
            autoComplete="current-password"
            error={errors.password?.message}
            {...form.register('password')}
          />
          <Link
            to="/forgot-password"
            className="text-muted-foreground justify-self-end text-sm underline-offset-4 hover:underline"
          >
            {t('auth.forgotPassword')}
          </Link>
        </div>
        <Button type="submit" size="lg" disabled={isSubmitting}>
          {isSubmitting ? t('auth.loggingIn') : t('auth.login')}
        </Button>
      </form>
    </AuthLayout>
  )
}
