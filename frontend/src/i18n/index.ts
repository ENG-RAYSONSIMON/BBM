/**
 * UI language (English / Kiswahili). Kiswahili is the default; the choice is
 * kept on this device in localStorage ("bbm.lang"), like the theme.
 *
 * Text that isn't a dictionary key (e.g. a message already translated by the
 * server) is shown unchanged, so error messages can be passed through `t()`.
 */
import i18n from 'i18next'
import { initReactI18next, useTranslation } from 'react-i18next'

import { en } from './en'
import { sw } from './sw'

export const LANGUAGES = [
  { code: 'sw', label: 'Kiswahili' },
  { code: 'en', label: 'English' },
] as const
export type Language = (typeof LANGUAGES)[number]['code']

export const LANGUAGE_KEY = 'bbm.lang'
export const DEFAULT_LANGUAGE: Language = 'sw'

function isLanguage(value: unknown): value is Language {
  return LANGUAGES.some((language) => language.code === value)
}

function storedLanguage(): Language {
  try {
    const value = localStorage.getItem(LANGUAGE_KEY)
    return isLanguage(value) ? value : DEFAULT_LANGUAGE
  } catch {
    return DEFAULT_LANGUAGE
  }
}

declare module 'i18next' {
  interface CustomTypeOptions {
    resources: { translation: typeof en }
  }
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, sw: { translation: sw } },
  lng: storedLanguage(),
  fallbackLng: 'en',
  supportedLngs: LANGUAGES.map((language) => language.code),
  // Server messages contain ":" and "." freely; never treat them as namespaces.
  nsSeparator: false,
  interpolation: { escapeValue: false }, // React escapes already
  returnNull: false,
})
document.documentElement.lang = i18n.language

i18n.on('languageChanged', (language) => {
  document.documentElement.lang = language
  try {
    localStorage.setItem(LANGUAGE_KEY, language)
  } catch {
    // Storage unavailable: the choice lasts until reload.
  }
})

/** The active language, for API headers and number/date formatting. */
export function currentLanguage(): Language {
  return isLanguage(i18n.language) ? i18n.language : DEFAULT_LANGUAGE
}

/**
 * Translate a message that may be a dictionary key (client validation) or
 * ready-made text (from the server). Unknown text comes back unchanged.
 */
export function translateMessage(message: string): string {
  return i18n.t(message as never, { defaultValue: message }) as string
}

/** `translateMessage` that re-renders when the language changes. */
export function useTranslateMessage(): (message: string | undefined) => string | undefined {
  const { t } = useTranslation()
  return (message) => (message ? (t(message as never, { defaultValue: message }) as string) : message)
}

export default i18n
