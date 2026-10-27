import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CopyIcon, KeyRoundIcon, PlusIcon, WandSparklesIcon } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import type { Control, FieldValues, Path, UseFormSetValue } from 'react-hook-form'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { DataList, PAGE_SIZE } from '@/components/data-list'
import type { Column } from '@/components/data-list'
import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { PageHeader } from '@/components/page-header'
import { RefSelect } from '@/components/ref-select'
import { SearchInput } from '@/components/search-input'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useTranslateMessage } from '@/i18n'
import { api, APP_URL } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { formatDateTime } from '@/lib/format'
import { applyServerErrors } from '@/lib/forms'
import { makeTempPassword, roleLabel } from '@/lib/roles'
import { staffEditSchema, staffPasswordSchema, staffSchema } from '@/lib/schemas'
import type { StaffEditValues, StaffPasswordValues, StaffValues } from '@/lib/schemas'
import type { Paginated, Role, StaffMember } from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'

function personName(member: Pick<StaffMember, 'first_name' | 'last_name' | 'email'>) {
  return [member.first_name, member.last_name].filter(Boolean).join(' ') || member.email
}

function useRoles() {
  return useQuery({ queryKey: ['roles'], queryFn: () => api<Role[]>('/roles/'), staleTime: 60_000 })
}

/** Who works here, their role and access. Owner and Admin (staff.manage). */
export function StaffPage() {
  const { t } = useTranslation()
  const list = useListParams()
  const [adding, setAdding] = useState(false)
  const [managing, setManaging] = useState<StaffMember | null>(null)
  const STATUS_FILTERS = [
    { id: 'false', name: t('staff.off') },
    { id: 'all', name: t('staff.everyone') },
  ]
  const status = list.get('status')
  const filters = { is_active: status === 'all' ? '' : status || 'true' }
  const query = useQuery({
    queryKey: ['staff', list.page, list.search, filters],
    queryFn: () =>
      api<Paginated<StaffMember>>(
        `/staff/${toQuery({ page: list.page, page_size: PAGE_SIZE, search: list.search, ...filters })}`,
      ),
    placeholderData: (previous) => previous,
  })

  const addButton = (
    <Button size="lg" onClick={() => setAdding(true)}>
      <PlusIcon />
      {t('staff.add')}
    </Button>
  )
  const open = (member: StaffMember) => member.can_manage && setManaging(member)

  const columns: Column<StaffMember>[] = [
    {
      header: t('common.name'),
      cell: (m) => (
        <div className="min-w-0">
          <p className="truncate font-medium">
            {personName(m)}
            {m.is_you && <span className="text-muted-foreground font-normal"> {t('staff.you')}</span>}
          </p>
          <p className="text-muted-foreground truncate text-xs">{[m.email, m.phone].filter(Boolean).join(' · ')}</p>
        </div>
      ),
    },
    { header: t('staff.role'), cell: (m) => roleLabel(t, m.role_name) },
    { header: t('common.status'), cell: (m) => <StaffBadges member={m} /> },
    {
      header: t('staff.lastLogin'),
      cell: (m) => (m.last_login ? formatDateTime(m.last_login) : t('staff.never')),
      className: 'text-right',
    },
  ]

  return (
    <div className="mx-auto grid max-w-6xl gap-4">
      <PageHeader title={t('staff.title')} description={t('staff.subtitle')} actions={addButton} />

      <div className="grid gap-3 sm:grid-cols-3">
        <SearchInput
          className="sm:col-span-2"
          value={list.search}
          onChange={list.setSearch}
          placeholder={t('staff.searchPlaceholder')}
        />
        <RefSelect hideLabel label={t('common.status')} noneLabel={t('staff.active')} value={status}
          onChange={(v) => list.set('status', v)} options={STATUS_FILTERS} />
      </div>

      <DataList
        label={t('staff.listLabel')}
        query={query}
        columns={columns}
        rowKey={(m) => m.id}
        onRowClick={open}
        page={list.page}
        onPageChange={list.setPage}
        empty={
          list.search || status
            ? { title: t('staff.noMatch'), description: t('common.noMatchHint') }
            : { title: t('staff.empty'), description: t('staff.emptyText'), action: addButton }
        }
        card={(m) => (
          <Card
            className="flex-row items-center gap-3 p-3"
            role={m.can_manage ? 'button' : undefined}
            tabIndex={m.can_manage ? 0 : undefined}
            onClick={() => open(m)}
            onKeyDown={(e) => e.key === 'Enter' && open(m)}
          >
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">
                {personName(m)}
                {m.is_you && <span className="text-muted-foreground font-normal"> {t('staff.you')}</span>}
              </p>
              <p className="text-muted-foreground truncate text-sm">{roleLabel(t, m.role_name)}</p>
            </div>
            <StaffBadges member={m} />
          </Card>
        )}
      />
      <p className="text-muted-foreground text-sm">{t('staff.rolesHint')}</p>

      <AddStaffDialog open={adding} onOpenChange={setAdding} />
      {managing && (
        <ManageStaffDialog member={managing} onOpenChange={(next) => !next && setManaging(null)} />
      )}
    </div>
  )
}

function StaffBadges({ member }: { member: StaffMember }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-wrap justify-end gap-1 md:justify-start">
      {member.is_active ? (
        <Badge variant="secondary">{t('staff.active')}</Badge>
      ) : (
        <Badge variant="destructive">{t('staff.off')}</Badge>
      )}
      {member.must_change_password && <Badge variant="outline">{t('staff.tempPasswordBadge')}</Badge>}
    </div>
  )
}

/** Role dropdown listing only the roles you may give. */
function RoleField<T extends FieldValues>({
  control,
  name,
  roles,
  error,
}: {
  control: Control<T>
  name: Path<T>
  roles: Role[] | undefined
  error?: string
}) {
  const { t } = useTranslation()
  const translate = useTranslateMessage()
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <div className="grid gap-1.5">
          <Label htmlFor="staff-role">{t('staff.role')}</Label>
          <Select value={field.value || undefined} onValueChange={field.onChange}>
            <SelectTrigger
              id="staff-role"
              aria-invalid={error ? true : undefined}
              className="w-full data-[size=default]:h-10 md:data-[size=default]:h-9"
            >
              <SelectValue placeholder={t('common.choose')} />
            </SelectTrigger>
            <SelectContent>
              {roles?.filter((r) => r.assignable).map((r) => (
                <SelectItem key={r.id} value={r.id}>
                  {roleLabel(t, r.name)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {error && <p className="text-destructive text-sm">{translate(error)}</p>}
        </div>
      )}
    />
  )
}

/** Temporary password input with a "make one for me" button. */
function TempPasswordField<T extends FieldValues & { temp_password: string }>({
  form,
  error,
  hint,
}: {
  form: { register: ReturnType<typeof useForm<T>>['register']; setValue: UseFormSetValue<T> }
  error?: string
  hint: string
}) {
  const { t } = useTranslation()
  const name = 'temp_password' as Path<T>
  return (
    <div className="grid gap-2">
      <FormField label={t('staff.tempPassword')} autoComplete="off" spellCheck={false} hint={hint} error={error}
        {...form.register(name)} />
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="justify-self-start"
        onClick={() => form.setValue(name, makeTempPassword() as T[typeof name], { shouldValidate: true })}
      >
        <WandSparklesIcon />
        {t('staff.makePassword')}
      </Button>
    </div>
  )
}

/** What to send the new person, ready to paste into WhatsApp or SMS. */
function LoginDetails({ email, password }: { email: string; password: string }) {
  const { me } = useAuth()
  const { t } = useTranslation()
  const text = t('staff.loginDetailsText', {
    business: me?.business.name ?? '',
    url: APP_URL,
    email,
    password,
  })

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(t('staff.copied'))
    } catch {
      toast.error(t('staff.copyFailed'))
    }
  }

  return (
    <div className="grid gap-3">
      <pre className="bg-muted rounded-md p-3 text-sm whitespace-pre-wrap">{text}</pre>
      <Button type="button" size="lg" onClick={copy}>
        <CopyIcon />
        {t('staff.copyDetails')}
      </Button>
    </div>
  )
}

function AddStaffDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const roles = useRoles()
  const [added, setAdded] = useState<{ member: StaffMember; password: string } | null>(null)
  const empty: StaffValues = { first_name: '', last_name: '', email: '', phone: '', role: '', temp_password: '' }
  const form = useForm<StaffValues>({ resolver: zodResolver(staffSchema), defaultValues: empty })
  const { errors, isSubmitting } = form.formState

  function close(next: boolean) {
    if (!next) {
      form.reset(empty)
      setAdded(null)
    }
    onOpenChange(next)
  }

  async function onSubmit(values: StaffValues) {
    let member: StaffMember
    try {
      member = await api<StaffMember>('/staff/', { method: 'POST', body: values })
    } catch (error) {
      applyServerErrors(error, form.setError, ['first_name', 'last_name', 'email', 'phone', 'role', 'temp_password'])
      return
    }
    await queryClient.invalidateQueries({ queryKey: ['staff'] })
    toast.success(t('staff.added', { name: personName(member) }))
    setAdded({ member, password: values.temp_password })
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90svh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{added ? t('staff.addedTitle') : t('staff.addTitle')}</DialogTitle>
          <DialogDescription>
            {added ? t('staff.sendDetails') : t('staff.addText')}
          </DialogDescription>
        </DialogHeader>
        {added ? (
          <>
            <LoginDetails email={added.member.email} password={added.password} />
            <DialogFooter>
              <Button variant="outline" size="lg" onClick={() => close(false)}>
                {t('common.close')}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <form id="add-staff" className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
              <FormError message={errors.root?.server?.message} />
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField label={t('auth.firstName')} autoFocus error={errors.first_name?.message}
                  {...form.register('first_name')} />
                <FormField label={t('auth.lastName')} error={errors.last_name?.message} {...form.register('last_name')} />
              </div>
              <FormField label={t('common.email')} type="email" autoComplete="off" error={errors.email?.message}
                {...form.register('email')} />
              <FormField label={t('auth.phoneOptional')} type="tel" error={errors.phone?.message}
                {...form.register('phone')} />
              <RoleField control={form.control} name="role" roles={roles.data} error={errors.role?.message} />
              <TempPasswordField form={form} error={errors.temp_password?.message} hint={t('staff.tempPasswordHint')} />
            </form>
            <DialogFooter>
              <Button variant="outline" size="lg" onClick={() => close(false)} disabled={isSubmitting}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" form="add-staff" size="lg" disabled={isSubmitting}>
                {isSubmitting ? t('common.saving') : t('staff.add')}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Change name, phone or role, turn access off/on, or give a new temporary password. */
function ManageStaffDialog({ member, onOpenChange }: { member: StaffMember; onOpenChange: (open: boolean) => void }) {
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const roles = useRoles()
  const [view, setView] = useState<'edit' | 'reset' | { password: string }>('edit')
  const name = personName(member)

  const editForm = useForm<StaffEditValues>({
    resolver: zodResolver(staffEditSchema),
    defaultValues: {
      first_name: member.first_name,
      last_name: member.last_name,
      phone: member.phone,
      role: member.role,
      is_active: member.is_active,
    },
  })
  const resetForm = useForm<StaffPasswordValues>({
    resolver: zodResolver(staffPasswordSchema),
    defaultValues: { temp_password: '' },
  })

  async function saveChanges(values: StaffEditValues) {
    try {
      await api(`/staff/${member.id}/`, { method: 'PATCH', body: values })
    } catch (error) {
      applyServerErrors(error, editForm.setError, ['first_name', 'last_name', 'phone', 'role', 'is_active'])
      return
    }
    await queryClient.invalidateQueries({ queryKey: ['staff'] })
    toast.success(t('staff.saved', { name }))
    onOpenChange(false)
  }

  async function resetPassword(values: StaffPasswordValues) {
    try {
      await api(`/staff/${member.id}/reset-password/`, { method: 'POST', body: values })
    } catch (error) {
      applyServerErrors(error, resetForm.setError, ['temp_password'])
      return
    }
    await queryClient.invalidateQueries({ queryKey: ['staff'] })
    setView({ password: values.temp_password })
  }

  const editErrors = editForm.formState.errors
  const resetErrors = resetForm.formState.errors

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{name}</DialogTitle>
          <DialogDescription>
            {view === 'edit'
              ? member.email
              : view === 'reset'
                ? t('staff.resetText')
                : t('staff.resetDone')}
          </DialogDescription>
        </DialogHeader>

        {view === 'edit' && (
          <>
            <form id="manage-staff" className="grid gap-4" noValidate onSubmit={editForm.handleSubmit(saveChanges)}>
              <FormError message={editErrors.root?.server?.message} />
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField label={t('auth.firstName')} error={editErrors.first_name?.message}
                  {...editForm.register('first_name')} />
                <FormField label={t('auth.lastName')} error={editErrors.last_name?.message}
                  {...editForm.register('last_name')} />
              </div>
              <FormField label={t('auth.phoneOptional')} type="tel" error={editErrors.phone?.message}
                {...editForm.register('phone')} />
              <RoleField control={editForm.control} name="role" roles={roles.data} error={editErrors.role?.message} />
              <Controller
                control={editForm.control}
                name="is_active"
                render={({ field }) => (
                  <div className="flex items-start gap-3">
                    <Switch id="staff-active" checked={field.value} onCheckedChange={field.onChange} />
                    <div className="grid gap-1">
                      <Label htmlFor="staff-active">{t('staff.canLogIn')}</Label>
                      <p className="text-muted-foreground text-sm">{t('staff.canLogInHint')}</p>
                    </div>
                  </div>
                )}
              />
              <Button type="button" variant="outline" className="justify-self-start" onClick={() => setView('reset')}>
                <KeyRoundIcon />
                {t('staff.resetPassword')}
              </Button>
            </form>
            <DialogFooter>
              <Button variant="outline" size="lg" onClick={() => onOpenChange(false)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" form="manage-staff" size="lg" disabled={editForm.formState.isSubmitting}>
                {editForm.formState.isSubmitting ? t('common.saving') : t('common.saveChanges')}
              </Button>
            </DialogFooter>
          </>
        )}

        {view === 'reset' && (
          <>
            <form id="reset-staff" className="grid gap-4" noValidate onSubmit={resetForm.handleSubmit(resetPassword)}>
              <FormError message={resetErrors.root?.server?.message} />
              <TempPasswordField form={resetForm} error={resetErrors.temp_password?.message} hint={t('staff.resetHint')} />
            </form>
            <DialogFooter>
              <Button variant="outline" size="lg" onClick={() => setView('edit')}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" form="reset-staff" size="lg" disabled={resetForm.formState.isSubmitting}>
                {resetForm.formState.isSubmitting ? t('common.saving') : t('staff.resetPassword')}
              </Button>
            </DialogFooter>
          </>
        )}

        {typeof view === 'object' && (
          <>
            <LoginDetails email={member.email} password={view.password} />
            <DialogFooter>
              <Button variant="outline" size="lg" onClick={() => onOpenChange(false)}>
                {t('common.close')}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
