import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { applyServerErrors } from '@/lib/forms'
import { settingsSchema } from '@/lib/schemas'
import type { SettingsValues } from '@/lib/schemas'
import { PERMISSIONS } from '@/lib/types'
import type { BusinessSettings } from '@/lib/types'

const SETTINGS_KEY = ['settings'] as const

export function SettingsPage() {
  const { me } = useAuth()
  const { t } = useTranslation()
  if (!me) return null

  const { business } = me
  const profile: [string, string][] = [
    [t('common.name'), business.name],
    [t('settings.currency'), business.currency],
    [t('settings.tin'), business.tin],
    [t('common.phone'), business.phone],
    [t('common.email'), business.email],
    [t('common.address'), business.address],
  ]

  return (
    <div className="mx-auto grid max-w-3xl gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">{t('settings.title')}</h1>

      <Card>
        <CardHeader>
          <CardTitle>{t('settings.profile')}</CardTitle>
          <CardDescription>{t('settings.profileSoon')}</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-[8rem_1fr]">
            {profile.map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="break-words">{value || '—'}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>

      <BusinessSettingsCard />
    </div>
  )
}

function BusinessSettingsCard() {
  const { can } = useAuth()
  const { t } = useTranslation()
  const canManage = can(PERMISSIONS.settingsManage)
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: SETTINGS_KEY,
    queryFn: () => api<BusinessSettings>('/settings/'),
    enabled: can(PERMISSIONS.settingsView),
  })

  const form = useForm<SettingsValues>({ resolver: zodResolver(settingsSchema) })
  const { errors, isDirty, isSubmitting } = form.formState

  useEffect(() => {
    if (query.data) form.reset(toFormValues(query.data))
  }, [query.data, form])

  const mutation = useMutation({
    mutationFn: (values: SettingsValues) =>
      api<BusinessSettings>('/settings/', {
        method: 'PATCH',
        body: { ...values, tax_rate: values.tax_rate.toFixed(2) },
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(SETTINGS_KEY, data)
      toast.success(t('settings.saved'))
    },
  })

  async function onSubmit(values: SettingsValues) {
    try {
      await mutation.mutateAsync(values)
    } catch (error) {
      applyServerErrors(error, form.setError, ['low_stock_threshold', 'expiry_warning_days', 'tax_rate'])
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.stockTax')}</CardTitle>
        <CardDescription>{canManage ? t('settings.appliesToAll') : t('settings.onlyManagers')}</CardDescription>
      </CardHeader>
      <CardContent>
        {!can(PERMISSIONS.settingsView) || (query.error instanceof ApiError && query.error.status === 403) ? (
          <p className="text-muted-foreground text-sm">{t('settings.noAccess')}</p>
        ) : query.isPending ? (
          <div className="grid gap-4" role="status" aria-label={t('settings.loadingSettings')}>
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        ) : query.isError ? (
          <div className="grid justify-items-start gap-3">
            <FormError message={query.error.message} />
            <Button variant="outline" size="lg" onClick={() => query.refetch()}>
              {t('common.tryAgain')}
            </Button>
          </div>
        ) : (
          <form className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
            <FormError message={errors.root?.server?.message} />
            <fieldset disabled={!canManage} className="grid gap-4 sm:grid-cols-2">
              <FormField
                label={t('settings.lowStockAt')}
                type="number"
                inputMode="numeric"
                min={0}
                hint={t('settings.lowStockHint')}
                error={errors.low_stock_threshold?.message}
                {...form.register('low_stock_threshold', { valueAsNumber: true })}
              />
              <FormField
                label={t('settings.expiryWarning')}
                type="number"
                inputMode="numeric"
                min={0}
                hint={t('settings.expiryWarningHint')}
                error={errors.expiry_warning_days?.message}
                {...form.register('expiry_warning_days', { valueAsNumber: true })}
              />
              <FormField
                label={t('settings.taxRate')}
                type="number"
                inputMode="decimal"
                min={0}
                max={100}
                step="0.01"
                error={errors.tax_rate?.message}
                {...form.register('tax_rate', { valueAsNumber: true })}
              />
            </fieldset>
            {canManage && (
              <div className="flex gap-2">
                <Button type="submit" size="lg" disabled={!isDirty || isSubmitting}>
                  {isSubmitting ? t('common.saving') : t('common.saveChanges')}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="lg"
                  disabled={!isDirty || isSubmitting}
                  onClick={() => query.data && form.reset(toFormValues(query.data))}
                >
                  {t('common.cancel')}
                </Button>
              </div>
            )}
          </form>
        )}
      </CardContent>
    </Card>
  )
}

function toFormValues(settings: BusinessSettings): SettingsValues {
  return {
    low_stock_threshold: settings.low_stock_threshold,
    expiry_warning_days: settings.expiry_warning_days,
    tax_rate: Number(settings.tax_rate),
  }
}
