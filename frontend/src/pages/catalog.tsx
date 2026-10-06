import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import type { FieldValues, Resolver } from 'react-hook-form'
import { toast } from 'sonner'

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
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import type { RefKind } from '@/lib/catalog'
import { applyServerErrors } from '@/lib/forms'
import { categorySchema, supplierSchema } from '@/lib/schemas'
import { PERMISSIONS } from '@/lib/types'
import type { Paginated } from '@/lib/types'
import { toQuery, useListParams } from '@/lib/use-list-params'

type Entity = { id: string; name: string } & Record<string, string>
type Field = { name: string; label: string; multiline?: boolean; type?: string }

type Config = {
  label: string
  singular: string
  schema: typeof categorySchema | typeof supplierSchema
  fields: Field[]
  subtitle: (item: Entity) => string
}

const CONFIG: Record<RefKind, Config> = {
  categories: {
    label: 'Categories',
    singular: 'category',
    schema: categorySchema,
    fields: [
      { name: 'name', label: 'Name' },
      { name: 'description', label: 'Description (optional)', multiline: true },
    ],
    subtitle: (c) => c.description,
  },
  brands: {
    label: 'Brands',
    singular: 'brand',
    schema: categorySchema,
    fields: [
      { name: 'name', label: 'Name' },
      { name: 'description', label: 'Description (optional)', multiline: true },
    ],
    subtitle: (b) => b.description,
  },
  suppliers: {
    label: 'Suppliers',
    singular: 'supplier',
    schema: supplierSchema,
    fields: [
      { name: 'name', label: 'Name' },
      { name: 'contact_person', label: 'Contact person (optional)' },
      { name: 'phone', label: 'Phone (optional)', type: 'tel' },
      { name: 'email', label: 'Email (optional)', type: 'email' },
      { name: 'address', label: 'Address (optional)', multiline: true },
      { name: 'notes', label: 'Notes (optional)', multiline: true },
    ],
    subtitle: (s) => [s.contact_person, s.phone, s.email].filter(Boolean).join(' · '),
  },
}

const KINDS = Object.keys(CONFIG) as RefKind[]

/** Categories, brands and suppliers used to organise products. */
export function CatalogPage() {
  const list = useListParams()
  const kind = (KINDS as string[]).includes(list.get('tab')) ? (list.get('tab') as RefKind) : 'categories'

  return (
    <div className="mx-auto grid max-w-4xl gap-4">
      <PageHeader title="Catalog setup" description="Categories, brands and suppliers for your products." />
      <Tabs
        value={kind}
        onValueChange={(next) => list.setMany({ search: '', tab: next === 'categories' ? '' : next })}
      >
        <TabsList>
          {KINDS.map((k) => (
            <TabsTrigger key={k} value={k}>
              {CONFIG[k].label}
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
      Add {config.singular}
    </Button>
  )
  const deleteButton = (item: Entity) =>
    canDelete && (
      <Button
        variant="ghost"
        size="icon-lg"
        aria-label={`Delete ${item.name}`}
        onClick={(event) => {
          event.stopPropagation()
          setDeleting(item)
        }}
      >
        <Trash2Icon />
      </Button>
    )

  const columns: Column<Entity>[] = [
    { header: 'Name', cell: (item) => <span className="font-medium">{item.name}</span> },
    { header: kind === 'suppliers' ? 'Contact' : 'Description', cell: (item) => config.subtitle(item) || '—' },
    ...(canDelete ? [{ header: 'Actions', cell: deleteButton, className: 'w-16 text-right' }] : []),
  ]

  return (
    <div className="grid gap-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <SearchInput className="flex-1" value={list.search} onChange={list.setSearch}
          placeholder={`Search ${config.label.toLowerCase()}`} />
        {addButton}
      </div>
      <DataList
        label={config.label.toLowerCase()}
        query={query}
        columns={columns}
        rowKey={(item) => item.id}
        onRowClick={canManage ? (item) => setEditing(item) : undefined}
        page={list.page}
        onPageChange={list.setPage}
        empty={
          list.search
            ? { title: `No ${config.label.toLowerCase()} match “${list.search}”` }
            : { title: `No ${config.label.toLowerCase()} yet`, action: addButton }
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
        title={`Delete ${deleting?.name}?`}
        description={`This can't be undone. A ${config.singular} that products still use can't be deleted.`}
        confirmLabel="Delete"
        destructive
        onConfirm={async () => {
          await api(`/${kind}/${deleting!.id}/`, { method: 'DELETE' })
          await queryClient.invalidateQueries({ queryKey: [kind] })
          toast.success(`${deleting!.name} deleted.`)
        }}
      />
    </div>
  )
}

function EditDialog({ kind, item, onClose }: { kind: RefKind; item: Entity | null; onClose: () => void }) {
  const config = CONFIG[kind]
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
    toast.success(item ? 'Saved.' : `${values.name} added.`)
    onClose()
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{item ? `Edit ${item.name}` : `Add ${config.singular}`}</DialogTitle>
        </DialogHeader>
        <form id="ref-form" className="grid gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <FormError message={errors.root?.server?.message} />
          {config.fields.map((field) => {
            const error = errors[field.name]?.message as string | undefined
            return field.multiline ? (
              <div key={field.name} className="grid gap-1.5">
                <Label htmlFor={`ref-${field.name}`}>{field.label}</Label>
                <Textarea id={`ref-${field.name}`} rows={2} {...form.register(field.name)} />
                {error && <p className="text-destructive text-sm">{error}</p>}
              </div>
            ) : (
              <FormField key={field.name} label={field.label} type={field.type} error={error}
                {...form.register(field.name)} />
            )
          })}
        </form>
        <DialogFooter>
          <Button variant="outline" size="lg" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" form="ref-form" size="lg" disabled={isSubmitting}>
            {isSubmitting ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
