import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { StaffPage } from './staff'
import { mockFetch } from '@/test/fetch-mock'
import { EMPTY_PAGE, page } from '@/test/fixtures'
import { renderWithAuth } from '@/test/render'
import type { Role, StaffMember } from '@/lib/types'

const ROUTES = { '/staff': <StaffPage /> }
const PERMS = ['staff.manage']

const ROLES: Role[] = [
  { id: 'r-admin', name: 'Admin', is_system: true, permissions: [], assignable: true },
  { id: 'r-cashier', name: 'Cashier', is_system: true, permissions: [], assignable: true },
  { id: 'r-owner', name: 'Owner', is_system: true, permissions: [], assignable: false },
  { id: 'r-seller', name: 'Seller', is_system: true, permissions: [], assignable: true },
]

function member(overrides: Partial<StaffMember> = {}): StaffMember {
  return {
    id: 'm-neema',
    email: 'neema@example.com',
    first_name: 'Neema',
    last_name: 'Juma',
    phone: '',
    role: 'r-seller',
    role_name: 'Seller',
    is_active: true,
    must_change_password: true,
    last_login: null,
    is_you: false,
    can_manage: true,
    created_at: '2026-10-20T08:00:00Z',
    ...overrides,
  }
}

const OWNER = member({
  id: 'm-owner',
  email: 'owner@example.com',
  first_name: 'Amina',
  last_name: '',
  role: 'r-owner',
  role_name: 'Owner',
  must_change_password: false,
  last_login: '2026-10-26T07:00:00Z',
  is_you: true,
  can_manage: false,
})

function routes(extra: Parameters<typeof mockFetch>[0] = {}) {
  return {
    'GET /staff/': { status: 200, body: page([OWNER, member()]) },
    'GET /roles/': { status: 200, body: ROLES },
    ...extra,
  }
}

describe('StaffPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists staff with their role and status', async () => {
    mockFetch(routes())
    renderWithAuth('/staff', ROUTES, PERMS)

    const table = await screen.findByRole('table', { name: 'staff' })
    const neema = within(table).getByText('Neema Juma').closest('tr')!
    expect(within(neema).getByText('Seller')).toBeInTheDocument()
    expect(within(neema).getByText('Temporary password')).toBeInTheDocument()
    expect(within(neema).getByText('Never')).toBeInTheDocument()
    expect(within(table).getByText('(you)')).toBeInTheDocument()
  })

  it('shows the empty state and an error state', async () => {
    mockFetch(routes({ 'GET /staff/': { status: 200, body: EMPTY_PAGE } }))
    renderWithAuth('/staff', ROUTES, PERMS)
    expect(await screen.findByText('Only you so far')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('shows an error with a retry button', async () => {
    mockFetch(routes({ 'GET /staff/': { status: 500, body: null } }))
    renderWithAuth('/staff', ROUTES, PERMS)
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('adds a seller and gives login details to send', async () => {
    const fetchMock = mockFetch(
      routes({
        'POST /staff/': [
          { status: 400, body: { email: ['This email already has an account. Use a different email.'] } },
          { status: 201, body: member({ id: 'm-new', email: 'zawadi@example.com', first_name: 'Zawadi', last_name: '' }) },
        ],
      }),
    )
    renderWithAuth('/staff', ROUTES, PERMS)
    const user = userEvent.setup()

    await user.click((await screen.findAllByRole('button', { name: 'Add staff' }))[0])
    let dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Add staff' }))
    expect(await within(dialog).findByText('Choose a role.')).toBeInTheDocument()
    expect(within(dialog).getByText('Use at least 8 characters.')).toBeInTheDocument()
    expect(fetchMock.count('POST /staff/')).toBe(0)

    await user.type(within(dialog).getByLabelText('First name'), 'Zawadi')
    await user.type(within(dialog).getByLabelText('Email'), 'zawadi@example.com')
    await user.click(within(dialog).getByLabelText('Role'))
    // Only roles you may give are offered.
    expect(screen.queryByRole('option', { name: 'Owner' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('option', { name: 'Seller' }))
    dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Make one for me' }))
    const password = (within(dialog).getByLabelText('Temporary password') as HTMLInputElement).value
    expect(password.length).toBeGreaterThanOrEqual(8)

    await user.click(within(dialog).getByRole('button', { name: 'Add staff' }))
    expect(await within(dialog).findByText('This email already has an account. Use a different email.')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Add staff' }))
    expect(await within(dialog).findByText('Staff member added')).toBeInTheDocument()
    expect(within(dialog).getByText(new RegExp(`Temporary password: ${password}`))).toBeInTheDocument()
    // The live site's address, not wherever this page happens to run.
    expect(within(dialog).getByText(/https:\/\/bbm\.mauzo\.tz/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Copy login details' })).toBeInTheDocument()

    const body = JSON.parse(String(fetchMock.calls.filter((c) => c.key === 'POST /staff/')[1].init.body))
    expect(body).toMatchObject({ email: 'zawadi@example.com', first_name: 'Zawadi', role: 'r-seller', temp_password: password })
  }, 15_000) // many steps; slow when the whole suite runs at once

  it('turns a staff member off', async () => {
    const fetchMock = mockFetch(routes({ 'PATCH /staff/m-neema/': { status: 200, body: member({ is_active: false }) } }))
    renderWithAuth('/staff', ROUTES, PERMS)
    const user = userEvent.setup()

    await user.click(within(await screen.findByRole('table', { name: 'staff' })).getByText('Neema Juma'))
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('switch', { name: 'Can log in' }))
    await user.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    const call = fetchMock.calls.find((c) => c.key === 'PATCH /staff/m-neema/')!
    expect(JSON.parse(String(call.init.body))).toEqual({
      first_name: 'Neema', last_name: 'Juma', phone: '', role: 'r-seller', is_active: false,
    })
  })

  it('changes name and phone, and shows why a shared account is refused', async () => {
    const refused = "This person also uses their account at another business, so their name and phone can't be changed here."
    const fetchMock = mockFetch(routes({
      'PATCH /staff/m-neema/': [
        { status: 400, body: { non_field_errors: [refused] } },
        { status: 200, body: member({ last_name: 'Mushi', phone: '0712345678' }) },
      ],
    }))
    renderWithAuth('/staff', ROUTES, PERMS)
    const user = userEvent.setup()

    await user.click(within(await screen.findByRole('table', { name: 'staff' })).getByText('Neema Juma'))
    const dialog = screen.getByRole('dialog')
    const lastName = within(dialog).getByLabelText('Last name')
    await user.clear(lastName)
    await user.type(lastName, 'Mushi')
    await user.type(within(dialog).getByLabelText(/Phone/), '0712345678')
    await user.click(within(dialog).getByRole('button', { name: 'Save changes' }))
    expect(await within(dialog).findByText(refused)).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Save changes' }))
    const calls = fetchMock.calls.filter((c) => c.key === 'PATCH /staff/m-neema/')
    expect(calls).toHaveLength(2)
    expect(JSON.parse(String(calls[1].init.body))).toMatchObject({ last_name: 'Mushi', phone: '0712345678' })
  })

  it("doesn't open someone you can't manage", async () => {
    mockFetch(routes())
    renderWithAuth('/staff', ROUTES, PERMS)
    await userEvent.setup().click(within(await screen.findByRole('table', { name: 'staff' })).getByText('Amina'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
