import { PackageIcon } from 'lucide-react'

import type { Product } from '@/lib/types'
import { cn } from '@/lib/utils'

export function ProductThumb({ product, className = 'size-10' }: { product: Product; className?: string }) {
  return product.image ? (
    <img src={product.image} alt="" className={cn('shrink-0 rounded-md border object-cover', className)} />
  ) : (
    <div className={cn('bg-muted text-muted-foreground flex shrink-0 items-center justify-center rounded-md', className)}>
      <PackageIcon className="size-1/2" />
    </div>
  )
}
