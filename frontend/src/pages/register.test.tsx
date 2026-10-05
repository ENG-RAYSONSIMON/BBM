import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RegisterPage } from './register'
import { mockFetch } from '@/test/fetch-mock'
import { renderRoute } from '@/test/render'

describe('RegisterPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows server field errors under the matching field', async () => {
    mockFetch({
      'POST /auth/register/': {
        status: 400,
        body: { email: ['A user with this email already exists.'] },
      },
    })
    renderRoute('/register', <RegisterPage />)
    const user = userEvent.setup()

    await user.type(screen.getByLabelText('Business name'), 'Glow Cosmetics')
    await user.type(screen.getByLabelText('Email'), 'owner@example.com')
    await user.type(screen.getByLabelText('Password'), 'Str0ng-Passw0rd!')
    await user.type(screen.getByLabelText('Confirm password'), 'Str0ng-Passw0rd!')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    const email = screen.getByLabelText('Email')
    expect(await screen.findByText('A user with this email already exists.')).toBeInTheDocument()
    expect(email).toHaveAttribute('aria-invalid', 'true')
  })

  it('checks that the passwords match before calling the server', async () => {
    const fetchMock = mockFetch({})
    renderRoute('/register', <RegisterPage />)
    const user = userEvent.setup()

    await user.type(screen.getByLabelText('Business name'), 'Glow Cosmetics')
    await user.type(screen.getByLabelText('Email'), 'owner@example.com')
    await user.type(screen.getByLabelText('Password'), 'Str0ng-Passw0rd!')
    await user.type(screen.getByLabelText('Confirm password'), 'different')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('Passwords do not match.')).toBeInTheDocument()
    expect(fetchMock.calls).toHaveLength(0)
  })
})
