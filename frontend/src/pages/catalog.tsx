import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import type { FieldValues, Resolver } from 'react-hook-form'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '@/components/confirm-dialog'
import { DataList, PAGE_SIZE } from '@/components/data-list'
import type { Column } from '@/components/data-list'
import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { PageHeader } from '@/components/page-header'
import { SearchInput } from '@/components/search-input'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { useTranslateMessage } from '@/i18n'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import type { RefKind } from '@/lib/catalog'
import { applyServerErrors } from '@/lib/forms'
import { categorySchema, supplierSchema } from '@/lib/schemas'
import { PERMISSIONS } from '@/lib/types'
import type { Paginated } from '@/lib/types'
import type { en } from '@/i18n/en'
import { toQuery, useListParams } from '@/lib/use-list-params'

type Entity = { id: string; name: string } & Record<string, string>
type FieldLabel = `common.${keyof typeof en.common}` | `catalog.${keyof typeof en.catalog}`
type Field = { name: string; label: FieldLabel; multiline?: boolean; type?: string }

// Tab names, buttons and empty states are keys: catalog.<kind>, catalog.add_<kind>, …
type Config = {
  schema: typeof categorySchema | typeof supplierSchema
  fields: Field[]
  subtitle: (item: Entity) => string
}

const CONFIG: Record<RefKind, Config> = {
  categories: {
    schema: categorySchema,
    fields: [
      { name: 'name', label: 'common.name' },
      { name: 'description', label: 'common.descriptionOptional', multiline: true },
    ],
    subtitle: (c) => c.description,
  },
  brands: {
    schema: categorySchema,
    fields: [
      { name: 'name', label: 'common.name' },
      { name: 'description', label: 'common.descriptionOptional', multiline: true },
    ],
    subtitle: (b) => b.description,
  },
  suppliers: {
    schema: supplierSchema,
    fields: [
      { name: 'name', label: 'common.name' },
      { name: 'contact_person', label: 'catalog.contactPerson' },
      { name: 'phone', label: 'catalog.phoneOptional', type: 'tel' },
      { name: 'email', label: 'catalog.emailOptional', type: 'email' },
      { name: 'address', label: 'catalog.addressOptional', multiline: true },
      { name: 'notes', label: 'catalog.notesOptional', multiline: true },
    ],
    subtitle: (s) => [s.contact_person, s.phone, s.email].filter(Boolean).join(' · '),
  },
}

const KINDS = Object.keys(CONFIG) as RefKind[]

/** Categories, brands and suppliers used to organise products. */
export function CatalogPage() {
  const list = useListParams()
  const { t } = useTranslation()
  const kind = (KINDS as string[]).includes(list.get('tab')) ? (list.get('tab') as RefKind) : 'categories'

  return (
    <div className="mx-auto grid max-w-4xl gap-4">
      <PageHeader title={t('catalog.title')} description={t('catalog.subtitle')} />
      <Tabs
        value={kind}
        onValueChange={(next) => list.setMany({ search: '', tab: next === 'categories' ? '' : next })}
      >
        <TabsList>
          {KINDS.map((k) => (
            <TabsTrigger key={k} value={k}>
              {t(`catalog.${k}`)}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <RefManager key={kind} kind={kind} />
    </div>
  )
}

function RefManager({ kind }: { kind: RefKind }) {
  const config = CONFIG[kind]
  const { can } = useAuth()
  const { t } = useTranslation()
  const list = useListParams()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<Entity | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Entity | null>(null)

  const query = useQuery({
    queryKey: [kind, list.page, list.search],
    queryFn: () =>
      api<Paginated<Entity>>(`/${kind}/${toQuery({ page: list.page, page_size: PAGE_SIZE, search: list.search })}`),
    placeholderData: (previous) => previous,
  })

  const canManage = can(PERMISSIONS.catalogManage)
  const canDelete = can(PERMISSIONS.catalogDelete)
  const addButton = canManage && (
    <Button size="lg" onClick={() => setEditing('new')}>
      <PlusIcon />
      {t(`catalog.add_${kind}`)}
    </Button>
  )
  const deleteButton = (item: Entity) =>
    canDelete && (
      <Button
        variant="ghost"
        size="icon-lg"
        aria-label={t('catalog.deleteItem', { name: item.name })}
        onClick={(event) => {
          event.stopPropagation()
          setDeleting(item)
        }}
      >
        <Trash2Icon />
      </Button>
    )

  const columns: Column<Entity>[] = [
    { header: t('common.name'), cell: (item) => <span className="font-medium">{item.name}</span> },
    {
      header: kind === 'suppliers' ? t('catalog.contact') : t('common.description'),
      cell: (item) => config.subtitle(item) || '—',
    },
    ...(canDelete ? [{ header: t('common.actions'), cell: deleteButton, className: 'w-16 text-right' }] : []),
  ]

  return (
    <div className="grid gap-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <SearchInput className="flex-1" value={list.search} onChange={list.setSearch}
          placeholder={t(`catalog.search_${kind}`)} />
        {addButton}
      </div>
      <DataList
        label={t(`catalog.${kind}`).toLowerCase()}
        query={query}
        columns={columns}
        rowKey={(item) => item.id}
        onRowClick={canManage ? (item) => setEditing(item) : undefined}
        page={list.page}
        onPageChange={list.setPage}
        empty={
          list.search
            ? { title: t('catalog.noMatch', { search: list.search }) }
            : { title: t(`catalog.empty_${kind}`), action: addButton }
        }
        card={(item) => (
          <Card className="flex-row items-center gap-2 p-3">
            <button
              type="button"
              className="min-w-0 flex-1 text-left"
              disabled={!canManage}
              onClick={() => setEditing(item)}
            >
              <p className="truncate font-medium">{item.name}</p>
              {config.subtitle(item) && (
                <p className="text-muted-foreground truncate text-sm">{config.subtitle(item)}</p>
              )}
            </button>
            {deleteButton(item)}
          </Card>
        )}
      />

      {editing && (
        <EditDialog
          kind={kind}
          item={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={t('catalog.deleteTitle', { name: deleting?.name ?? '' })}
        description={t('catalog.deleteText')}
        confirmLabel={t('common.delete')}
        destructive
        onConfirm={async () => {
          await api(`/${kind}/${deleting!.id}/`, { method: 'DELETE' })
          await queryClient.invalidateQueries({ queryKey: [kind] })
          toast.success(t('catalog.deleted', { name: deleting!.name }))
        }}
      />
    </div>
  )
}

function EditDialog({ kind, item, onClose }: { kind: RefKind; item: Entity | null; onClose: () => void }) {
  const config = CONFIG[kind]
  const { t } = useTranslation()
  const translate = useTranslateMessage()
  const queryClient = useQueryClient()
  const defaults = Object.fromEntries(config.fields.map((f) => [f.name, item?.[f.name] ?? '']))
  const form = useForm<FieldValues>({
    resolver: zodResolver(config.schema) as unknown as Resolver<FieldValues>,
    defaultValues: defaults,
  })
  const { errors, isSubmitting } = form.formState

  async function onSubmit(values: FieldValues) {
    try {
      if (item) await api(`/${kind}/${item.id}/`, { method: 'PATCH', body: values })
      else await api(`/${kind}/`, { method: 'POST', body: values })
    } catch (error) {
      applyServerErrors(error, form.setError, config.fields.map((f) => f.name))
      return
    }
    await queryClient.invalidateQueries({ queryKey: [kind] })
    toast.success(item ? t('catalog.saved') : t('catalog.added', { name: values.name }))
    onClose()
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{item ? t('catalog.editTitle', { name: item.name }) : t(`catalog.add_${kind}`)}</DialogTitle>
        </DialogHeader>
        <form id="ref-form" className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <FormError message={errors.root?.server?.message} />
          {config.fields.map((field) => {
            const error = errors[field.name]?.message as string | undefined
            return field.multiline ? (
              <div key={field.name} className="grid gap-1.5">
                <Label htmlFor={`ref-${field.name}`}>{t(field.label)}</Label>
                <Textarea id={`ref-${field.name}`} rows={2} {...form.register(field.name)} />
                {error && <p className="text-destructive text-sm">{translate(error)}</p>}
              </div>
            ) : (
              <FormField key={field.name} label={t(field.label)} type={field.type} error={error}
                {...form.register(field.name)} />
            )
          })}
        </form>
        <DialogFooter>
          <Button variant="outline" size="lg" onClick={onClose} disabled={isSubmitting}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form="ref-form" size="lg" disabled={isSubmitting}>
            {isSubmitting ? t('common.saving') : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
