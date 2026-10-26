import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SidebarContent } from './sidebar-content'
import { renderWithAuth } from '@/test/render'

describe('SidebarContent', () => {
  it('only links to pages the role may open', async () => {
    renderWithAuth('/sidebar', { '/sidebar': <SidebarContent /> }, ['settings.view'])
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    expect(nav).toHaveTextContent('Dashboard')
    expect(nav).toHaveTextContent('Settings')
    expect(nav).not.toHaveTextContent('Products')
    expect(nav).not.toHaveTextContent('Inventory alerts')
    expect(nav).not.toHaveTextContent('Audit log')
  })

  it('shows reports with reports.view', async () => {
    renderWithAuth('/sidebar', { '/sidebar': <SidebarContent /> }, ['reports.view'])
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(nav).toHaveTextContent('Reports')
    expect(nav).not.toHaveTextContent('Audit log')
  })

  it('shows staff only with staff.manage, and everyone their password link', async () => {
    renderWithAuth('/sidebar', { '/sidebar': <SidebarContent /> }, ['sales.view'])
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(nav).not.toHaveTextContent('Staff')
    expect(screen.getByRole('link', { name: 'My password' })).toHaveAttribute('href', '/change-password')
  })

  it('shows the staff link with staff.manage', async () => {
    renderWithAuth('/sidebar', { '/sidebar': <SidebarContent /> }, ['staff.manage'])
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(nav).toHaveTextContent('Staff')
  })

  it('shows the audit log only with audit.view', async () => {
    renderWithAuth('/sidebar', { '/sidebar': <SidebarContent /> }, ['audit.view'])
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(nav).toHaveTextContent('Audit log')
  })

  it('shows catalog and inventory links with their permissions', async () => {
    renderWithAuth('/sidebar', { '/sidebar': <SidebarContent /> }, ['catalog.view', 'inventory.view'])
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    expect(nav).toHaveTextContent('Products')
    expect(nav).toHaveTextContent('Inventory alerts')
    expect(nav).toHaveTextContent('Catalog setup')
    expect(nav).not.toHaveTextContent('Settings')
  })

  it('shows selling links only with sales permissions', async () => {
    renderWithAuth('/sidebar', { '/sidebar': <SidebarContent /> }, ['sales.view'])
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    expect(nav).toHaveTextContent('Sales')
    expect(nav).toHaveTextContent('Customers')
    expect(nav).not.toHaveTextContent('New sale')
  })

  it('shows purchases and expenses links with their permissions', async () => {
    renderWithAuth('/sidebar', { '/sidebar': <SidebarContent /> }, ['purchases.view', 'expenses.view'])
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    expect(nav).toHaveTextContent('Purchases')
    expect(nav).toHaveTextContent('Expenses')
    expect(nav).not.toHaveTextContent('Sales')
  })
})
