import {
  BarChart3Icon,
  BellRingIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  PackageIcon,
  ReceiptIcon,
  SettingsIcon,
  ShieldCheckIcon,
  ShoppingCartIcon,
  TagsIcon,
  TruckIcon,
  UsersIcon,
  WalletIcon,
} from 'lucide-react'
import type { ComponentType } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, useNavigate } from 'react-router'

import { Brand } from './brand'
import { LanguageToggle } from '@/components/language-toggle'
import { NotificationBell } from '@/components/notification-bell'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-context'
import { PERMISSIONS } from '@/lib/types'
import { cn } from '@/lib/utils'

type NavItem = {
  to: string
  label: NavLabel
  icon: ComponentType<{ className?: string }>
  /** Shown only to roles holding this permission. */
  permission?: string
}

type NavLabel =
  | 'dashboard' | 'newSale' | 'sales' | 'customers' | 'purchases' | 'expenses'
  | 'products' | 'inventory' | 'catalog' | 'settings' | 'reports' | 'audit'

// Only features that exist get a link. Labels are keys under `nav`.
const NAV: NavItem[] = [
  { to: '/', label: 'dashboard', icon: LayoutDashboardIcon },
  { to: '/pos', label: 'newSale', icon: ShoppingCartIcon, permission: PERMISSIONS.salesCreate },
  { to: '/sales', label: 'sales', icon: ReceiptIcon, permission: PERMISSIONS.salesView },
  { to: '/customers', label: 'customers', icon: UsersIcon, permission: PERMISSIONS.salesView },
  { to: '/purchases', label: 'purchases', icon: TruckIcon, permission: PERMISSIONS.purchasesView },
  { to: '/expenses', label: 'expenses', icon: WalletIcon, permission: PERMISSIONS.expensesView },
  { to: '/products', label: 'products', icon: PackageIcon, permission: PERMISSIONS.catalogView },
  { to: '/inventory', label: 'inventory', icon: BellRingIcon, permission: PERMISSIONS.inventoryView },
  { to: '/catalog', label: 'catalog', icon: TagsIcon, permission: PERMISSIONS.catalogView },
  { to: '/reports', label: 'reports', icon: BarChart3Icon, permission: PERMISSIONS.reportsView },
  { to: '/settings', label: 'settings', icon: SettingsIcon, permission: PERMISSIONS.settingsView },
  { to: '/audit', label: 'audit', icon: ShieldCheckIcon, permission: PERMISSIONS.auditView },
]

/**
 * Sidebar body, shared by the fixed desktop sidebar and the mobile drawer.
 * `onNavigate` lets the drawer close when a link is chosen.
 */
export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { me, logout, can } = useAuth()
  const { t } = useTranslation()
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
      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-3" aria-label={t('nav.main')}>
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
            {t(`nav.${item.label}`)}
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
          <NotificationBell onNavigate={onNavigate} />
          <LanguageToggle />
          <ThemeToggle />
        </div>
        <Button variant="ghost" size="lg" className="w-full justify-start" onClick={handleLogout}>
          <LogOutIcon />
          {t('nav.logout')}
        </Button>
      </div>
    </div>
  )
}
