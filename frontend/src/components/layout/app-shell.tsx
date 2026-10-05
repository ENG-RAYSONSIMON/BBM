import { MenuIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router'

import { Brand } from './brand'
import { SidebarContent } from './sidebar-content'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { useAuth } from '@/lib/auth-context'

/** Desktop (md+): fixed sidebar. Mobile: top bar whose menu opens the sidebar as a drawer. */
export function AppShell() {
  const { me } = useAuth()
  const { pathname } = useLocation()
  // The page the drawer was opened on. Any page change (link, back button,
  // redirect) closes it without an extra effect.
  const [openOn, setOpenOn] = useState<string | null>(null)
  const menuOpen = openOn === pathname
  const setMenuOpen = (open: boolean) => setOpenOn(open ? pathname : null)

  // The drawer is mobile-only; close it if the window grows to desktop width.
  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 768px)')
    const close = () => desktop.matches && setOpenOn(null)
    desktop.addEventListener('change', close)
    return () => desktop.removeEventListener('change', close)
  }, [])

  return (
    <div className="bg-muted/40 min-h-svh md:flex">
      <aside className="bg-background hidden w-64 shrink-0 border-r md:sticky md:top-0 md:block md:h-svh">
        <SidebarContent />
      </aside>

      <header className="bg-background sticky top-0 z-20 flex h-14 items-center gap-2 border-b px-2 md:hidden">
        <Button
          variant="ghost"
          size="icon-lg"
          aria-label="Open menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(true)}
        >
          <MenuIcon />
        </Button>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Brand compact />
          <span className="truncate font-medium">{me?.business.name}</span>
        </div>
        <ThemeToggle />
      </header>

      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent side="left" className="w-72 gap-0 p-0 md:hidden">
          <SheetTitle className="sr-only">Menu</SheetTitle>
          <SheetDescription className="sr-only">Pages and account</SheetDescription>
          <SidebarContent onNavigate={() => setMenuOpen(false)} />
        </SheetContent>
      </Sheet>

      <main className="min-w-0 flex-1 px-4 py-6 md:px-8 md:py-8">
        <Outlet />
      </main>
    </div>
  )
}
