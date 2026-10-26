import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PasswordField } from './password-field'

describe('PasswordField', () => {
  it('shows and hides what was typed without submitting the form', async () => {
    const onSubmit = vi.fn((event: SubmitEvent) => event.preventDefault())
    render(
      <form onSubmit={(e) => onSubmit(e.nativeEvent as SubmitEvent)}>
        <PasswordField label="Password" />
        <PasswordField label="Confirm password" />
      </form>,
    )
    const user = userEvent.setup()
    const input = screen.getByLabelText('Password')
    await user.type(input, 'Siri-2026')
    expect(input).toHaveAttribute('type', 'password')

    const [eye] = screen.getAllByRole('button', { name: 'Show password' })
    await user.click(eye)
    expect(input).toHaveAttribute('type', 'text')
    expect(input).toHaveValue('Siri-2026')
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true')
    // Each field has its own eye.
    expect(screen.getByLabelText('Confirm password')).toHaveAttribute('type', 'password')

    await user.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(input).toHaveAttribute('type', 'password')
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
