import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'

import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { AuthLayout } from '@/components/layout/auth-layout'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-context'
import { applyServerErrors } from '@/lib/forms'
import { registerSchema } from '@/lib/schemas'
import type { RegisterValues } from '@/lib/schemas'

export function RegisterPage() {
  const { register: registerOwner } = useAuth()
  const navigate = useNavigate()

  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      business_name: '',
      first_name: '',
      last_name: '',
      phone: '',
      email: '',
      password: '',
      confirm_password: '',
    },
  })
  const { errors, isSubmitting } = form.formState

  async function onSubmit(values: RegisterValues) {
    try {
      await registerOwner({
        business_name: values.business_name,
        first_name: values.first_name,
        last_name: values.last_name,
        phone: values.phone,
        email: values.email,
        password: values.password,
      })
      navigate('/', { replace: true })
    } catch (error) {
      applyServerErrors(error, form.setError, [
        'business_name',
        'first_name',
        'last_name',
        'phone',
        'email',
        'password',
      ])
    }
  }

  return (
    <AuthLayout
      title="Create your business account"
      description="You'll be the owner. You can add staff later."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="text-foreground font-medium underline-offset-4 hover:underline">
            Log in
          </Link>
        </>
      }
    >
      <form className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        <FormError message={errors.root?.server?.message} />
        <FormField
          label="Business name"
          autoComplete="organization"
          error={errors.business_name?.message}
          {...form.register('business_name')}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="First name"
            autoComplete="given-name"
            error={errors.first_name?.message}
            {...form.register('first_name')}
          />
          <FormField
            label="Last name"
            autoComplete="family-name"
            error={errors.last_name?.message}
            {...form.register('last_name')}
          />
        </div>
        <FormField
          label="Phone (optional)"
          type="tel"
          autoComplete="tel"
          placeholder="+255…"
          error={errors.phone?.message}
          {...form.register('phone')}
        />
        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...form.register('email')}
        />
        <FormField
          label="Password"
          type="password"
          autoComplete="new-password"
          hint="At least 8 characters. Avoid common or all-number passwords."
          error={errors.password?.message}
          {...form.register('password')}
        />
        <FormField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          error={errors.confirm_password?.message}
          {...form.register('confirm_password')}
        />
        <Button type="submit" size="lg" disabled={isSubmitting}>
          {isSubmitting ? 'Creating account…' : 'Create account'}
        </Button>
      </form>
    </AuthLayout>
  )
}
