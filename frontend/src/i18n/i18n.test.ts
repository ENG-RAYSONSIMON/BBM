import { afterEach, describe, expect, it, vi } from 'vitest'

import { en } from './en'
import { sw } from './sw'

/** "a.b.c" → value, for every string in a nested dictionary. */
function flatten(tree: object, prefix = ''): Record<string, string> {
  return Object.entries(tree).reduce<Record<string, string>>((out, [key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return typeof value === 'string' ? { ...out, [path]: value } : { ...out, ...flatten(value, path) }
  }, {})
}

const placeholders = (text: string) => [...text.matchAll(/{{(\w+)}}/g)].map((m) => m[1]).sort()

// The setup file switches the shared instance to English; load a fresh one.
async function freshI18n() {
  vi.resetModules()
  return import('./index')
}

describe('dictionaries', () => {
  const english = flatten(en)
  const swahili = flatten(sw)

  it('have the same keys', () => {
    expect(Object.keys(swahili).sort()).toEqual(Object.keys(english).sort())
  })

  it('have no empty Swahili text', () => {
    expect(Object.entries(swahili).filter(([, value]) => !value.trim())).toEqual([])
  })

  it('use the same {{placeholders}} in both languages', () => {
    const mismatched = Object.keys(english).filter(
      (key) => placeholders(english[key]).join() !== placeholders(swahili[key]).join(),
    )
    expect(mismatched).toEqual([])
  })
})

describe('language choice', () => {
  afterEach(() => localStorage.clear())

  it('starts in Kiswahili on a new device', async () => {
    const { default: i18n } = await freshI18n()
    expect(i18n.language).toBe('sw')
    expect(document.documentElement.lang).toBe('sw')
    expect(i18n.t('nav.sales')).toBe('Mauzo')
  })

  it('remembers the choice on this device', async () => {
    localStorage.setItem('bbm.lang', 'en')
    expect((await freshI18n()).default.language).toBe('en')

    localStorage.setItem('bbm.lang', 'fr') // not offered: back to the default
    expect((await freshI18n()).default.language).toBe('sw')
  })

  it('saves a change and updates <html lang>', async () => {
    const { default: i18n } = await freshI18n()
    await i18n.changeLanguage('en')
    expect(localStorage.getItem('bbm.lang')).toBe('en')
    expect(document.documentElement.lang).toBe('en')
  })

  it('passes server messages through untranslated', async () => {
    const { translateMessage } = await freshI18n()
    expect(translateMessage('errors.enterName')).toBe('Weka jina.')
    expect(translateMessage('Shea Butter: zimebaki 1 tu.')).toBe('Shea Butter: zimebaki 1 tu.')
  })
})
