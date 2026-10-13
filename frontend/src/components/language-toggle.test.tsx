import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useTranslation } from 'react-i18next'
import { describe, expect, it } from 'vitest'

import { LanguageToggle } from './language-toggle'

function SalesLabel() {
  const { t } = useTranslation()
  return <p>{t('nav.sales')}</p>
}

async function pick(language: 'Kiswahili' | 'English') {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /Change language|Badilisha lugha/ }))
  await user.click(await screen.findByRole('menuitemradio', { name: language }))
}

describe('LanguageToggle', () => {
  it('switches the whole UI to Kiswahili and back, remembering the choice', async () => {
    render(
      <>
        <LanguageToggle />
        <SalesLabel />
      </>,
    )
    expect(screen.getByText('Sales')).toBeInTheDocument()

    await pick('Kiswahili')
    expect(await screen.findByText('Mauzo')).toBeInTheDocument()
    expect(localStorage.getItem('bbm.lang')).toBe('sw')
    expect(document.documentElement.lang).toBe('sw')
    expect(screen.getByRole('button', { name: 'Badilisha lugha' })).toBeInTheDocument()

    await pick('English')
    expect(await screen.findByText('Sales')).toBeInTheDocument()
    expect(localStorage.getItem('bbm.lang')).toBe('en')
  })
})
