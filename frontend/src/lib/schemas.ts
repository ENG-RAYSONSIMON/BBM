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
