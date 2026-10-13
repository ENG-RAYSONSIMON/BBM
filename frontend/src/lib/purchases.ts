// Purchase form maths. Amounts are whole cents (see money.ts); the server
// recomputes every total.
import { toCents } from './money'

/** One purchase line as typed. Amounts stay strings until submit. */
export type PurchaseLine = {
  key: string
  product: string
  productName: string
  tracksExpiry: boolean
  quantity: string
  unitCost: string
  batchNumber: string
  expiryDate: string
}

/** Line problems the server would refuse, as i18n keys, so they show before saving. */
export function lineError(line: PurchaseLine): string | undefined {
  if (!/^[1-9]\d*$/.test(line.quantity.trim())) return 'errors.lineQuantity'
  if (line.unitCost.trim() === '' || toCents(line.unitCost) === null) return 'errors.lineUnitCost'
  if (line.tracksExpiry && !line.batchNumber.trim()) return 'errors.lineBatch'
  return undefined
}

/** quantity × unit cost in cents, or 0 while the line is incomplete. */
export function lineAmount(line: PurchaseLine): number {
  const quantity = Number(line.quantity)
  const cost = toCents(line.unitCost)
  return Number.isInteger(quantity) && quantity > 0 && cost !== null ? quantity * cost : 0
}

/** Total of the lines, in cents. */
export function purchaseTotal(lines: PurchaseLine[]): number {
  return lines.reduce((sum, line) => sum + lineAmount(line), 0)
}
