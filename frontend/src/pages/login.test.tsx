import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LoginPage } from './login'
import { AUTH_PAYLOAD, ME, mockFetch } from '@/test/fetch-mock'
import { renderRoute } from '@/test/render'

async function fillAndSubmit() {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Email'), 'owner@example.com')
  await user.type(screen.getByLabelText('Password'), 'Str0ng-Passw0rd!')
  await user.click(screen.getByRole('button', { name: 'Log in' }))
  return user
}

describe('LoginPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('asks which business when the account has several, then logs in to it', async () => {
    const fetchMock = mockFetch({
      'POST /auth/login/': (init) =>
        JSON.parse(String(init.body)).business_id === 'b2'
          ? { status: 200, body: AUTH_PAYLOAD }
          : {
              status: 400,
              body: {
                business_id: ['This account belongs to several businesses; choose one.'],
                businesses: [
                  { id: 'b1', name: 'Glow Cosmetics' },
                  { id: 'b2', name: 'Shine Beauty' },
                ],
              },
            },
      'GET /auth/me/': { status: 200, body: ME },
    })
    renderRoute('/login', <LoginPage />)

    const user = await fillAndSubmit()
    await user.click(await screen.findByRole('button', { name: 'Shine Beauty' }))

    expect(await screen.findByText('Home')).toBeInTheDocument()
    const lastLogin = fetchMock.calls.filter((c) => c.key === 'POST /auth/login/').at(-1)!
    expect(JSON.parse(String(lastLogin.init.body))).toMatchObject({ business_id: 'b2' })
    expect(localStorage.getItem('bbm.refresh')).toBe('refresh-1')
  })

  it('shows one generic message for bad credentials', async () => {
    mockFetch({
      'POST /auth/login/': {
        status: 401,
        body: { detail: 'No active account found with the given credentials.' },
      },
    })
    renderRoute('/login', <LoginPage />)

    await fillAndSubmit()

    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.')
  })

  it('tells the user when they are rate limited', async () => {
    mockFetch({ 'POST /auth/login/': { status: 429, body: { detail: 'Request was throttled.' } } })
    renderRoute('/login', <LoginPage />)

    await fillAndSubmit()

    expect(await screen.findByRole('alert')).toHaveTextContent(/too many attempts/i)
  })
})
