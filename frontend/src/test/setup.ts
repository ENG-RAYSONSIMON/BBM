import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach } from 'vitest'

import i18n from '@/i18n'

// jsdom lacks these browser APIs; next-themes and Radix menus need them.
window.matchMedia ??= (query: string) =>
  ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }) as MediaQueryList
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.releasePointerCapture ??= () => {}
Element.prototype.scrollIntoView ??= () => {}

// Tests read English text; Kiswahili has its own tests.
beforeEach(async () => {
  await i18n.changeLanguage('en')
  localStorage.removeItem('bbm.lang') // tests start as a new device
})

afterEach(() => {
  cleanup()
  localStorage.clear()
  document.documentElement.className = ''
})
