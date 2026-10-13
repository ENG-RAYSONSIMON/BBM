// Client-side validation mirroring the backend serializers (NFR-2). The
// server still validates everything; these only give faster feedback.
// Messages are i18n keys (src/i18n); FormField / FormError translate them.
import { z } from 'zod'

const email = z.email('errors.email').max(254)
const newPassword = z.string().min(8, 'errors.passwordShort')

export const loginSchema = z.object({
  email,
  password: z.string().min(1, 'errors.enterPassword'),
})
export type LoginValues = z.infer<typeof loginSchema>

export const registerSchema = z
  .object({
    business_name: z.string().trim().min(1, 'errors.enterBusinessName').max(255),
    first_name: z.string().trim().max(150),
    last_name: z.string().trim().max(150),
    phone: z.string().trim().max(20),
    email,
    password: newPassword,
    confirm_password: z.string(),
  })
  .refine((v) => v.password === v.confirm_password, {
    path: ['confirm_password'],
    message: 'errors.passwordsDontMatch',
  })
export type RegisterValues = z.infer<typeof registerSchema>

export const forgotPasswordSchema = z.object({ email })
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>

export const resetPasswordSchema = z
  .object({ new_password: newPassword, confirm_password: z.string() })
  .refine((v) => v.new_password === v.confirm_password, {
    path: ['confirm_password'],
    message: 'errors.passwordsDontMatch',
  })
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>

const wholeNumber = z
  .number({ error: 'errors.enterNumber' })
  .int('errors.wholeNumber')
  .min(0, 'errors.zeroOrMore')

export const settingsSchema = z.object({
  low_stock_threshold: wholeNumber,
  expiry_warning_days: wholeNumber,
  tax_rate: z
    .number({ error: 'errors.enterNumber' })
    .min(0, 'errors.between0And100')
    .max(100, 'errors.between0And100'),
  // loyalty_enabled is left out until loyalty exists (Phase 5).
})
export type SettingsValues = z.infer<typeof settingsSchema>

// ---- Phase 2: catalog & inventory ------------------------------------------
// Number inputs are kept as strings in the form and converted on submit, so
// an empty optional field stays empty instead of becoming NaN.

const money = z
  .string()
  .trim()
  .min(1, 'errors.enterAmount')
  .regex(/^\d+(\.\d{1,2})?$/, 'errors.moneyFormat')

const optionalWholeNumber = z
  .string()
  .trim()
  .regex(/^\d*$/, 'errors.wholeNumber')
  .transform((v) => (v === '' ? null : Number(v)))

const optionalId = z.string().transform((v) => (v === '' ? null : v))

export const productSchema = z.object({
  name: z.string().trim().min(1, 'errors.enterProductName').max(255),
  description: z.string().trim(),
  sku: z.string().trim().max(64),
  barcode: z.string().trim().max(64),
  unit: z.string().trim().min(1, 'errors.enterUnit').max(20),
  category: optionalId,
  brand: optionalId,
  supplier: optionalId,
  selling_price: money,
  cost_price: money,
  reorder_level: optionalWholeNumber,
  tracks_expiry: z.boolean(),
})
export type ProductFormInput = z.input<typeof productSchema>
export type ProductPayload = z.output<typeof productSchema>

export const categorySchema = z.object({
  name: z.string().trim().min(1, 'errors.enterName').max(100),
  description: z.string().trim(),
})
export type CategoryValues = z.infer<typeof categorySchema>

export const supplierSchema = z.object({
  name: z.string().trim().min(1, 'errors.enterName').max(255),
  contact_person: z.string().trim().max(255),
  phone: z.string().trim().max(20),
  email: z.union([z.literal(''), z.email('errors.email')]),
  address: z.string().trim(),
  notes: z.string().trim(),
})
export type SupplierValues = z.infer<typeof supplierSchema>

export const adjustmentSchema = z
  .object({
    kind: z.string().min(1, 'errors.chooseWhatHappened'),
    batch: z.string(), // existing batch id, or 'new'
    batch_number: z.string().trim().max(64),
    expiry_date: z.string(),
    quantity: z
      .string()
      .trim()
      .regex(/^[1-9]\d*$/, 'errors.quantityAboveZero')
      .transform(Number),
    reason: z.string().trim().min(1, 'errors.addShortNote').max(255),
  })
export type AdjustmentInput = z.input<typeof adjustmentSchema>
export type AdjustmentValues = z.output<typeof adjustmentSchema>

// ---- Phase 3: sales ----------------------------------------------------------

export const customerSchema = z.object({
  name: z.string().trim().min(1, 'errors.enterCustomerName').max(255),
  phone: z.string().trim().max(20),
  notes: z.string().trim(),
})
export type CustomerValues = z.infer<typeof customerSchema>

export const paymentSchema = z.object({
  amount_received: money.refine((v) => Number(v) > 0, 'errors.enterCashReceived'),
  note: z.string().trim().max(255),
})
export type PaymentValues = z.infer<typeof paymentSchema>

export const voidSchema = z.object({
  reason: z.string().trim().min(1, 'errors.voidReason').max(255),
})
export type VoidValues = z.infer<typeof voidSchema>

// ---- Phase 3 step 2: expenses -----------------------------------------------

export const expenseSchema = z.object({
  category: z.string().min(1, 'errors.chooseCategory'),
  amount: money.refine((v) => Number(v) > 0, 'errors.amountAboveZero'),
  expense_date: z.string().min(1, 'errors.chooseDate'),
  description: z.string().trim().min(1, 'errors.expenseDescription').max(255),
  paid_to: z.string().trim().max(255),
})
export type ExpenseValues = z.infer<typeof expenseSchema>

export const cancelPurchaseSchema = z.object({
  reason: z.string().trim().min(1, 'errors.cancelPurchaseReason').max(255),
})
export type CancelPurchaseValues = z.infer<typeof cancelPurchaseSchema>
