import type { TFunction } from 'i18next'

// The seeded system roles have translated names; a business's own roles
// show as typed.
const SYSTEM_ROLES = ['Owner', 'Admin', 'Seller', 'Cashier'] as const
type SystemRole = (typeof SYSTEM_ROLES)[number]

export function roleLabel(t: TFunction, name: string): string {
  return (SYSTEM_ROLES as readonly string[]).includes(name) ? t(`roles.${name as SystemRole}`) : name
}

/** A readable temporary password, e.g. "Duka-4821-Rose". */
export function makeTempPassword(): string {
  const words = ['Duka', 'Rose', 'Shea', 'Aloe', 'Mafuta', 'Sabuni', 'Lulu', 'Nuru', 'Zuri', 'Tamu']
  const values = crypto.getRandomValues(new Uint32Array(3))
  const pick = (n: number) => words[n % words.length]
  return `${pick(values[0])}-${String(1000 + (values[1] % 9000))}-${pick(values[2])}`
}
