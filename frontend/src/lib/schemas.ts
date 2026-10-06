// Client-side validation mirroring the backend serializers (NFR-2). The
// server still validates everything; these only give faster feedback.
import { z } from 'zod'

const email = z.email('Enter a valid email address.').max(254)
const newPassword = z.string().min(8, 'Use at least 8 characters.')

export const loginSchema = z.object({
  email,
  password: z.string().min(1, 'Enter your password.'),
})
export type LoginValues = z.infer<typeof loginSchema>

export const registerSchema = z
  .object({
    business_name: z.string().trim().min(1, 'Enter your business name.').max(255),
    first_name: z.string().trim().max(150),
    last_name: z.string().trim().max(150),
    phone: z.string().trim().max(20),
    email,
    password: newPassword,
    confirm_password: z.string(),
  })
  .refine((v) => v.password === v.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match.',
  })
export type RegisterValues = z.infer<typeof registerSchema>

export const forgotPasswordSchema = z.object({ email })
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>

export const resetPasswordSchema = z
  .object({ new_password: newPassword, confirm_password: z.string() })
  .refine((v) => v.new_password === v.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match.',
  })
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>

const wholeNumber = z
  .number({ error: 'Enter a number.' })
  .int('Use a whole number.')
  .min(0, 'Must be 0 or more.')

export const settingsSchema = z.object({
  low_stock_threshold: wholeNumber,
  expiry_warning_days: wholeNumber,
  tax_rate: z
    .number({ error: 'Enter a number.' })
    .min(0, 'Must be between 0 and 100.')
    .max(100, 'Must be between 0 and 100.'),
  // loyalty_enabled is left out until loyalty exists (Phase 5).
})
export type SettingsValues = z.infer<typeof settingsSchema>

// ---- Phase 2: catalog & inventory ------------------------------------------
// Number inputs are kept as strings in the form and converted on submit, so
// an empty optional field stays empty instead of becoming NaN.

const money = z
  .string()
  .trim()
  .min(1, 'Enter an amount.')
  .regex(/^\d+(\.\d{1,2})?$/, 'Use a number like 15000 or 15000.50.')

const optionalWholeNumber = z
  .string()
  .trim()
  .regex(/^\d*$/, 'Use a whole number.')
  .transform((v) => (v === '' ? null : Number(v)))

const optionalId = z.string().transform((v) => (v === '' ? null : v))

export const productSchema = z.object({
  name: z.string().trim().min(1, 'Enter the product name.').max(255),
  description: z.string().trim(),
  sku: z.string().trim().max(64),
  barcode: z.string().trim().max(64),
  unit: z.string().trim().min(1, 'Enter a unit, e.g. pcs.').max(20),
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
  name: z.string().trim().min(1, 'Enter a name.').max(100),
  description: z.string().trim(),
})
export type CategoryValues = z.infer<typeof categorySchema>

export const supplierSchema = z.object({
  name: z.string().trim().min(1, 'Enter a name.').max(255),
  contact_person: z.string().trim().max(255),
  phone: z.string().trim().max(20),
  email: z.union([z.literal(''), z.email('Enter a valid email address.')]),
  address: z.string().trim(),
  notes: z.string().trim(),
})
export type SupplierValues = z.infer<typeof supplierSchema>

export const adjustmentSchema = z
  .object({
    kind: z.string().min(1, 'Choose what happened.'),
    batch: z.string(), // existing batch id, or 'new'
    batch_number: z.string().trim().max(64),
    expiry_date: z.string(),
    quantity: z
      .string()
      .trim()
      .regex(/^[1-9]\d*$/, 'Enter a whole number above 0.')
      .transform(Number),
    reason: z.string().trim().min(1, 'Add a short note.').max(255),
  })
export type AdjustmentInput = z.input<typeof adjustmentSchema>
export type AdjustmentValues = z.output<typeof adjustmentSchema>
