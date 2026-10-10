import {
  BellRingIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  PackageIcon,
  ReceiptIcon,
  SettingsIcon,
  ShoppingCartIcon,
  TagsIcon,
  UsersIcon,
} from 'lucide-react'
import type { ComponentType } from 'react'
import { NavLink, useNavigate } from 'react-router'

import { Brand } from './brand'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-context'
import { PERMISSIONS } from '@/lib/types'
import { cn } from '@/lib/utils'

type NavItem = {
  to: string
  label: string
  icon: ComponentType<{ className?: string }>
  /** Shown only to roles holding this permission. */
  permission?: string
}

// Only features that exist get a link; purchases and expenses come next.
const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboardIcon },
  { to: '/pos', label: 'New sale', icon: ShoppingCartIcon, permission: PERMISSIONS.salesCreate },
  { to: '/sales', label: 'Sales', icon: ReceiptIcon, permission: PERMISSIONS.salesView },
  { to: '/customers', label: 'Customers', icon: UsersIcon, permission: PERMISSIONS.salesView },
  { to: '/products', label: 'Products', icon: PackageIcon, permission: PERMISSIONS.catalogView },
  { to: '/inventory', label: 'Inventory alerts', icon: BellRingIcon, permission: PERMISSIONS.inventoryView },
  { to: '/catalog', label: 'Catalog setup', icon: TagsIcon, permission: PERMISSIONS.catalogView },
  { to: '/settings', label: 'Settings', icon: SettingsIcon, permission: PERMISSIONS.settingsView },
]

/**
 * Sidebar body, shared by the fixed desktop sidebar and the mobile drawer.
 * `onNavigate` lets the drawer close when a link is chosen.
 */
export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { me, logout, can } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    onNavigate?.()
    await logout()
    navigate('/login', { replace: true })
  }

  const displayName =
    [me?.user.first_name, me?.user.last_name].filter(Boolean).join(' ') || me?.user.email

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center border-b px-4">
        <Brand />
      </div>
      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-3" aria-label="Main">
        {NAV.filter((item) => !item.permission || can(item.permission)).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex min-h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-muted text-foreground'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )
            }
          >
            <item.icon className="size-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <div className="mb-2 flex items-center gap-2 px-1">
          <div className="min-w-0 flex-1 text-sm">
            <p className="truncate font-medium">{me?.business.name}</p>
            <p className="text-muted-foreground truncate">
              {displayName} · {me?.role}
            </p>
          </div>
          <ThemeToggle />
        </div>
        <Button variant="ghost" size="lg" className="w-full justify-start" onClick={handleLogout}>
          <LogOutIcon />
          Log out
        </Button>
      </div>
    </div>
  )
}
