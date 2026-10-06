import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ImageIcon, XIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { FormError } from '@/components/form-error'
import { FormField } from '@/components/form-field'
import { PageHeader } from '@/components/page-header'
import { RefSelect } from '@/components/ref-select'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'
import { useRefOptions } from '@/lib/catalog'
import { applyServerErrors } from '@/lib/forms'
import { checkImageFile, IMAGE_TYPES } from '@/lib/images'
import { productSchema } from '@/lib/schemas'
import type { ProductFormInput, ProductPayload } from '@/lib/schemas'
import type { Product } from '@/lib/types'

const EMPTY: ProductFormInput = {
  name: '',
  description: '',
  sku: '',
  barcode: '',
  unit: 'pcs',
  category: '',
  brand: '',
  supplier: '',
  selling_price: '',
  cost_price: '',
  reorder_level: '',
  tracks_expiry: true,
}

function toFormValues(product: Product): ProductFormInput {
  return {
    name: product.name,
    description: product.description,
    sku: product.sku,
    barcode: product.barcode,
    unit: product.unit,
    category: product.category ?? '',
    brand: product.brand ?? '',
    supplier: product.supplier ?? '',
    selling_price: product.selling_price,
    cost_price: product.cost_price,
    reorder_level: product.reorder_level === null ? '' : String(product.reorder_level),
    tracks_expiry: product.tracks_expiry,
  }
}

/** /products/new and /products/:id/edit. */
export function ProductFormPage() {
  const { id } = useParams()
  const editing = Boolean(id)
  const productQuery = useQuery({
    queryKey: ['product', id],
    queryFn: () => api<Product>(`/products/${id}/`),
    enabled: editing,
  })

  if (editing && productQuery.isPending) {
    return (
      <div className="mx-auto grid max-w-3xl gap-4" role="status" aria-label="Loading product">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-96" />
      </div>
    )
  }
  if (editing && productQuery.isError) {
    return (
      <div className="mx-auto grid max-w-3xl justify-items-start gap-3">
        <FormError message={productQuery.error.message} />
        <Button variant="outline" size="lg" asChild>
          <Link to="/products">Back to products</Link>
        </Button>
      </div>
    )
  }
  return <ProductForm product={productQuery.data} />
}

function ProductForm({ product }: { product?: Product }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const categories = useRefOptions('categories')
  const brands = useRefOptions('brands')
  const suppliers = useRefOptions('suppliers')

  const form = useForm<ProductFormInput, unknown, ProductPayload>({
    resolver: zodResolver(productSchema),
    defaultValues: product ? toFormValues(product) : EMPTY,
  })
  const { errors, isSubmitting } = form.formState

  // Image: a newly picked file, or a request to remove the current one.
  const [file, setFile] = useState<File | null>(null)
  const [removeImage, setRemoveImage] = useState(false)
  const [imageError, setImageError] = useState<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const previewRef = useRef<string | null>(null)
  const shownImage = preview ?? (removeImage ? null : product?.image ?? null)

  function showPreview(next: File | null) {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    previewRef.current = next ? URL.createObjectURL(next) : null
    setPreview(previewRef.current)
  }
  useEffect(() => () => {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current)
  }, [])

  function pickFile(picked: File | undefined) {
    if (!picked) return
    const problem = checkImageFile(picked)
    setImageError(problem)
    if (!problem) {
      setFile(picked)
      showPreview(picked)
      setRemoveImage(false)
    }
  }

  async function onSubmit(values: ProductPayload) {
    let saved: Product
    try {
      saved = product
        ? await api<Product>(`/products/${product.id}/`, { method: 'PATCH', body: values })
        : await api<Product>('/products/', { method: 'POST', body: values })
    } catch (error) {
      applyServerErrors(error, form.setError, [
        'name', 'description', 'sku', 'barcode', 'unit', 'category', 'brand', 'supplier',
        'selling_price', 'cost_price', 'reorder_level', 'tracks_expiry',
      ])
      return
    }

    try {
      if (file) {
        const body = new FormData()
        body.append('image', file)
        await api(`/products/${saved.id}/image/`, { method: 'PUT', body })
      } else if (removeImage && product?.image) {
        await api(`/products/${saved.id}/image/`, { method: 'DELETE' })
      }
    } catch (error) {
      toast.error(`Product saved, but the image wasn't: ${(error as Error).message}`)
    }

    await queryClient.invalidateQueries({ queryKey: ['products'] })
    await queryClient.invalidateQueries({ queryKey: ['product', saved.id] })
    toast.success(product ? 'Product updated.' : 'Product added.')
    navigate(`/products/${saved.id}`, { replace: true })
  }

  const cancelTo = product ? `/products/${product.id}` : '/products'

  return (
    <form className="mx-auto grid max-w-3xl gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
      <PageHeader title={product ? `Edit ${product.name}` : 'Add product'} />
      <FormError message={errors.root?.server?.message} />

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <FormField label="Name" error={errors.name?.message} {...form.register('name')} />
          </div>
          <FormField label="SKU (optional)" error={errors.sku?.message} {...form.register('sku')} />
          <FormField label="Barcode (optional)" inputMode="numeric" error={errors.barcode?.message}
            {...form.register('barcode')} />
          {(['category', 'brand', 'supplier'] as const).map((field) => {
            const options = { category: categories, brand: brands, supplier: suppliers }[field].data
            return (
              <Controller
                key={field}
                control={form.control}
                name={field}
                render={({ field: input }) => (
                  <div className="grid gap-1.5">
                    <RefSelect
                      label={field[0].toUpperCase() + field.slice(1)}
                      value={input.value}
                      onChange={input.onChange}
                      options={options}
                    />
                    {errors[field] && <p className="text-destructive text-sm">{errors[field]?.message}</p>}
                  </div>
                )}
              />
            )
          })}
          <FormField label="Unit" hint="e.g. pcs, bottle, tube" error={errors.unit?.message} {...form.register('unit')} />
          <div className="grid gap-1.5 sm:col-span-2">
            <Label htmlFor="description">Description (optional)</Label>
            <Textarea id="description" rows={3} {...form.register('description')} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Prices and stock rules</CardTitle>
          <CardDescription>Prices in TZS. Changing them never changes past sales.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <FormField label="Selling price" inputMode="decimal" error={errors.selling_price?.message}
            {...form.register('selling_price')} />
          <FormField label="Cost (buying) price" inputMode="decimal" error={errors.cost_price?.message}
            {...form.register('cost_price')} />
          <FormField
            label="Low-stock alert at (optional)"
            inputMode="numeric"
            hint="Leave empty to use the business setting."
            error={errors.reorder_level?.message}
            {...form.register('reorder_level')}
          />
          <Controller
            control={form.control}
            name="tracks_expiry"
            render={({ field }) => (
              <div className="flex items-start gap-3 sm:pt-6">
                <Switch id="tracks_expiry" checked={field.value} onCheckedChange={field.onChange} />
                <div className="grid gap-1">
                  <Label htmlFor="tracks_expiry">Track expiry dates</Label>
                  <p className={errors.tracks_expiry ? 'text-destructive text-sm' : 'text-muted-foreground text-sm'}>
                    {errors.tracks_expiry?.message ?? 'Each batch gets an expiry date.'}
                  </p>
                </div>
              </div>
            )}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Image</CardTitle>
          <CardDescription>JPEG, PNG or WebP, up to 2 MB.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-4">
          {shownImage ? (
            <img src={shownImage} alt="Product" className="size-28 rounded-lg border object-cover" />
          ) : (
            <div className="bg-muted text-muted-foreground flex size-28 items-center justify-center rounded-lg">
              <ImageIcon className="size-8" />
            </div>
          )}
          <div className="grid gap-2">
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="lg" asChild>
                <label className="cursor-pointer">
                  {shownImage ? 'Change image' : 'Choose image'}
                  <input
                    type="file"
                    accept={IMAGE_TYPES.join(',')}
                    className="sr-only"
                    aria-label="Product image"
                    onChange={(event) => {
                      pickFile(event.target.files?.[0])
                      event.target.value = ''
                    }}
                  />
                </label>
              </Button>
              {shownImage && (
                <Button
                  type="button"
                  variant="ghost"
                  size="lg"
                  onClick={() => {
                    setFile(null)
                    showPreview(null)
                    setRemoveImage(true)
                  }}
                >
                  <XIcon />
                  Remove
                </Button>
              )}
            </div>
            {imageError && <p className="text-destructive text-sm" role="alert">{imageError}</p>}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" size="lg" asChild>
          <Link to={cancelTo}>Cancel</Link>
        </Button>
        <Button type="submit" size="lg" disabled={isSubmitting}>
          {isSubmitting ? 'Saving…' : product ? 'Save changes' : 'Add product'}
        </Button>
      </div>
    </form>
  )
}
