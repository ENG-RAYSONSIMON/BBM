import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from 'next-themes'
import { describe, expect, it } from 'vitest'

import { ThemeToggle } from './theme-toggle'

function renderToggle() {
  render(
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem storageKey="bbm.theme">
      <ThemeToggle />
    </ThemeProvider>,
  )
}

async function pick(label: 'Light' | 'Dark' | 'System') {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Change theme' }))
  await user.click(await screen.findByRole('menuitemradio', { name: label }))
}

describe('ThemeToggle', () => {
  it('switches to dark and remembers the choice', async () => {
    renderToggle()

    await pick('Dark')

    expect(document.documentElement).toHaveClass('dark')
    expect(localStorage.getItem('bbm.theme')).toBe('dark')
  })

  it('switches back to light', async () => {
    localStorage.setItem('bbm.theme', 'dark')
    renderToggle()
    expect(document.documentElement).toHaveClass('dark')

    await pick('Light')

    expect(document.documentElement).not.toHaveClass('dark')
    expect(localStorage.getItem('bbm.theme')).toBe('light')
  })
})
