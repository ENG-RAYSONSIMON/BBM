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
  })

  it('shows catalog and inventory links with their permissions', async () => {
    renderWithAuth('/sidebar', { '/sidebar': <SidebarContent /> }, ['catalog.view', 'inventory.view'])
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    expect(nav).toHaveTextContent('Products')
    expect(nav).toHaveTextContent('Inventory alerts')
    expect(nav).toHaveTextContent('Catalog setup')
    expect(nav).not.toHaveTextContent('Settings')
  })
})
