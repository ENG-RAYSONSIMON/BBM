// Cart and cash maths for the sale screen. Amounts are handled as whole
// cents so sums never pick up floating-point noise; the server recomputes
// everything from its own prices anyway (the client never sends a price).

const AMOUNT = /^\d+(\.\d{1,2})?$/

/** "12000" / "12000.5" / "12000.50" → cents; '' → 0; invalid → null. */
export function toCents(value: string): number | null {
  const text = value.trim().replace(/,/g, '')
  if (text === '') return 0
  if (!AMOUNT.test(text)) return null
  const [whole, fraction = ''] = text.split('.')
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
}

/** Cents → the API's decimal string, e.g. 1200050 → "12000.50". */
export function fromCents(cents: number): string {
  return (cents / 100).toFixed(2)
}

export type CartLine = {
  /** Unit price as the API's decimal string. */
  unitPrice: string
  quantity: number
  /** Discount for the whole line, as typed. */
  discount: string
}

export type CartTotals = {
  subtotal: number
  discount: number
  total: number
  /** Index → message for lines whose discount is invalid. */
  lineErrors: Record<number, string>
}

/** Subtotal, discounts and total, all in cents. */
export function cartTotals(lines: CartLine[]): CartTotals {
  let subtotal = 0
  let discount = 0
  const lineErrors: Record<number, string> = {}
  lines.forEach((line, index) => {
    const gross = (toCents(line.unitPrice) ?? 0) * line.quantity
    const lineDiscount = toCents(line.discount)
    subtotal += gross
    if (lineDiscount === null) {
      lineErrors[index] = 'Use a number like 1000.'
    } else if (lineDiscount > gross) {
      lineErrors[index] = 'The discount is more than the line.'
    } else {
      discount += lineDiscount
    }
  })
  return { subtotal, discount, total: subtotal - discount, lineErrors }
}

export type Tender = {
  /** Applied to the sale. */
  paid: number
  /** Given back to the customer. */
  change: number
  /** Left owed on credit. */
  balance: number
}

/** What happens to the cash handed over for a total (both in cents). */
export function tender(total: number, received: number): Tender {
  const paid = Math.min(received, total)
  return { paid, change: received - paid, balance: total - paid }
}
