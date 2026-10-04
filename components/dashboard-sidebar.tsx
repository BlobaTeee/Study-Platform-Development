'use client'

import { useAuth } from '@/lib/auth-context'
import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { useTranslations } from 'next-intl'
import { LanguageSwitch } from '@/components/language-switch'
import {
  BarChart3,
  ClipboardList,
  Home,
  LogOut,
  Menu,
  NotebookText,
  PanelLeftClose,
  PanelLeftOpen,
  X,
  type LucideIcon,
  UserRound,
} from 'lucide-react'

type NavItem = {
  href: string
  /** key under the `nav` namespace */
  label: 'home' | 'notebooks' | 'tests' | 'analytics'
  icon: LucideIcon
  /** tint used for the active state, one per study mode */
  activeClass: string
}

const navItems: NavItem[] = [
  {
    href: '/dashboard',
    label: 'home',
    icon: Home,
    activeClass: 'bg-mode-library/10 text-mode-library',
  },
  {
    href: '/dashboard/notebooks',
    label: 'notebooks',
    icon: NotebookText,
    activeClass: 'bg-mode-library/10 text-mode-library',
  },
  {
    href: '/dashboard/tests',
    label: 'tests',
    icon: ClipboardList,
    activeClass: 'bg-mode-quizzes/10 text-mode-quizzes',
  },
  {
    href: '/dashboard/analytics',
    label: 'analytics',
    icon: BarChart3,
    activeClass: 'bg-mode-analytics/10 text-mode-analytics',
  },
]

function useIsActive() {
  const pathname = usePathname()
  return (href: string) => {
    if (href === '/dashboard') return pathname === '/dashboard'
    return pathname === href || (pathname?.startsWith(href + '/') ?? false)
  }
}

/** A quiet monogram tile that stands in for a logo — Fraunces "S" on a paper-blue chip. */
function BrandMark() {
  return (
    <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-mode-library/10 text-mode-library font-display text-lg font-semibold leading-none">
      S
    </span>
  )
}

/**
 * The nav body shared by the desktop rail and the mobile drawer.
 * `collapsed` renders an icon-only rail; the mobile drawer is always expanded.
 */
function SidebarBody({
  collapsed,
  onNavigate,
  footerSlot,
}: {
  collapsed: boolean
  onNavigate?: () => void
  footerSlot?: React.ReactNode
}) {
  const { user, logout } = useAuth()
  const router = useRouter()
  const isActive = useIsActive()
  const t = useTranslations('nav')

  const handleLogout = () => {
    onNavigate?.()
    logout()
    router.push('/login')
  }

  return (
    <div className="flex h-full flex-col">
      <Link
        href="/dashboard"
        onClick={onNavigate}
        className={cn(
          'flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-slate-100',
          'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode-library/30',
          collapsed && 'justify-center px-0',
        )}
        title={collapsed ? 'StudyFlow' : undefined}
      >
        <BrandMark />
        {!collapsed && (
          <span className="block truncate font-display text-xl font-semibold leading-tight text-slate-900">
            StudyFlow
          </span>
        )}
      </Link>

      <nav className="mt-5 flex-1 space-y-0.5">
        {navItems.map((item) => {
          const active = isActive(item.href)
          const Icon = item.icon
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              title={collapsed ? t(item.label) : undefined}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'flex h-10 items-center gap-3 rounded-lg px-3 text-[15px] font-medium transition-colors',
                'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode-library/30',
                active
                  ? item.activeClass
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                collapsed && 'justify-center px-0',
              )}
            >
              <Icon className="size-[18px] shrink-0" strokeWidth={active ? 2.25 : 2} />
              {!collapsed && t(item.label)}
            </Link>
          )
        })}
      </nav>

      <div className="space-y-1 pt-4">
        {/* Two segments when there is room; on the icon-only rail, one square
            button showing the current code that switches on press — a reader
            who keeps the rail collapsed must still be able to find this. */}
        {collapsed ? (
          <div className="flex justify-center pb-1">
            <LanguageSwitch variant="toggle" />
          </div>
        ) : (
          <div className="px-3 pb-2">
            <LanguageSwitch compact />
          </div>
        )}
        {footerSlot}
        <Link
          href="/dashboard/account"
          title={collapsed ? t('account') : undefined}
          className={cn(
            'flex h-10 w-full items-center gap-3 rounded-lg px-3 text-[15px] font-medium transition-colors',
            isActive('/dashboard/account')
              ? 'bg-slate-100 text-slate-900'
              : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
            'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-slate-400/30',
            collapsed && 'justify-center px-0',
          )}
        >
          <UserRound className="size-[18px] shrink-0" />
          {!collapsed && <span className="truncate">{user?.username ?? t('account')}</span>}
        </Link>
        <button
          type="button"
          onClick={handleLogout}
          title={collapsed ? t('signOut') : undefined}
          className={cn(
            'flex h-10 w-full items-center gap-3 rounded-lg px-3 text-[15px] font-medium transition-colors',
            'text-slate-500 hover:bg-red-50 hover:text-mode-danger',
            'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-red-500/25',
            collapsed && 'justify-center px-0',
          )}
        >
          <LogOut className="size-[18px] shrink-0" />
          {!collapsed && t('signOut')}
        </button>
      </div>
    </div>
  )
}

const COLLAPSE_KEY = 'sf-sidebar-collapsed'

/** Persistent left rail on desktop. Collapses to an icon-only rail; state is remembered. */
export function AppSidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const t = useTranslations('nav')

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === '1')
    } catch {
      /* private mode / no storage — fall back to expanded */
    }
  }, [])

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0')
      } catch {
        /* ignore */
      }
      return next
    })
  }, [])

  return (
    <aside
      data-collapsed={collapsed}
      className={cn(
        'hidden md:flex shrink-0 flex-col border-r border-slate-200 bg-white p-3',
        'transition-[width] duration-200 ease-out motion-reduce:transition-none',
        collapsed ? 'w-[68px]' : 'w-60',
      )}
    >
      <SidebarBody
        collapsed={collapsed}
        footerSlot={
          <button
            type="button"
            onClick={toggle}
            title={collapsed ? t('expandSidebar') : t('collapseSidebar')}
            aria-label={collapsed ? t('expandSidebar') : t('collapseSidebar')}
            className={cn(
              'flex h-10 w-full items-center gap-3 rounded-lg px-3 text-[15px] font-medium transition-colors',
              'text-slate-500 hover:bg-slate-100 hover:text-slate-700',
              'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-slate-300',
              collapsed && 'justify-center px-0',
            )}
          >
            {collapsed ? (
              <PanelLeftOpen className="size-[18px] shrink-0" />
            ) : (
              <>
                <PanelLeftClose className="size-[18px] shrink-0" />
                {t('collapse')}
              </>
            )}
          </button>
        }
      />
    </aside>
  )
}

/** Mobile top bar with a hamburger that opens a full-height drawer. Hidden on desktop. */
export function MobileNavBar() {
  const [open, setOpen] = useState(false)
  const pathname = usePathname()
  const t = useTranslations('nav')

  // Close the drawer whenever the route changes.
  useEffect(() => {
    setOpen(false)
  }, [pathname])

  return (
    <>
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-4 md:hidden">
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label={t('openMenu')}
          className="grid size-11 place-items-center rounded-lg text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode-library/30"
        >
          <Menu className="size-5" />
        </button>
        <Link
          href="/dashboard"
          className="flex items-center gap-2 rounded-lg px-1 py-1 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode-library/30"
        >
          <BrandMark />
          <span className="font-display text-lg font-semibold text-slate-900">StudyFlow</span>
        </Link>
      </header>

      {open && (
        <>
          <div
            className="fixed inset-0 z-40 bg-slate-900/20 md:hidden"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <aside className="fixed left-0 top-0 z-50 h-full w-[min(300px,86vw)] border-r border-slate-200 bg-white p-4 shadow-2xl md:hidden">
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label={t('closeMenu')}
              className="absolute right-3 top-3 grid size-11 place-items-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-slate-300"
            >
              <X className="size-5" />
            </button>
            <SidebarBody collapsed={false} onNavigate={() => setOpen(false)} />
          </aside>
        </>
      )}
    </>
  )
}
