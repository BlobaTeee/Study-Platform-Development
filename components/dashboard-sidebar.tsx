'use client'

import { useAuth } from '@/lib/auth-context'
import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useCallback, useEffect, useRef, useState } from 'react'
import useSWR from 'swr'
import { analyticsAPI } from '@/lib/api'
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
  PenLine,
  X,
  type LucideIcon,
  UserRound,
} from 'lucide-react'

type NavItem = {
  href: string
  /** key under the `nav` namespace */
  label: 'home' | 'notebooks' | 'tests' | 'practice' | 'analytics'
  icon: LucideIcon
  /** the section's mode colour, for the active tab: the icon tile and the label */
  tile: string
  ink: string
}

const navItems: NavItem[] = [
  { href: '/dashboard', label: 'home', icon: Home, tile: 'bg-mode-library', ink: 'text-mode-library-ink' },
  { href: '/dashboard/notebooks', label: 'notebooks', icon: NotebookText, tile: 'bg-mode-library', ink: 'text-mode-library-ink' },
  { href: '/dashboard/tests', label: 'tests', icon: ClipboardList, tile: 'bg-mode-quizzes-ink', ink: 'text-mode-quizzes-ink' },
  { href: '/dashboard/practice', label: 'practice', icon: PenLine, tile: 'bg-mode-quizzes-ink', ink: 'text-mode-quizzes-ink' },
  { href: '/dashboard/analytics', label: 'analytics', icon: BarChart3, tile: 'bg-mode-analytics-ink', ink: 'text-mode-analytics-ink' },
]

function useIsActive() {
  const pathname = usePathname()
  return (href: string) => {
    if (href === '/dashboard') return pathname === '/dashboard'
    return pathname === href || (pathname?.startsWith(href + '/') ?? false)
  }
}

/** The name as the mark: "Study" upright, "Flow" in Fraunces italic in the
 *  library blue. The icon-only rail keeps just the italic S. */
function Wordmark({ compact = false, className }: { compact?: boolean; className?: string }) {
  if (compact) {
    return (
      <span className={cn('font-display text-2xl font-semibold italic leading-none text-mode-library-ink', className)} aria-hidden>
        S
      </span>
    )
  }
  return (
    <span className={cn('font-display text-xl font-semibold leading-tight text-slate-900', className)}>
      Study<span className="font-medium italic text-mode-library-ink">Flow</span>
    </span>
  )
}

/** Today's share of due cards, read from the same request as the home page. */
function useDueToday(): number {
  const { data } = useSWR(['/analytics/recommendations'], () => analyticsAPI.getRecommendations())
  const due = data?.data?.due
  if (!due) return 0
  return due.today ?? (due.due ?? 0) + (due.new ?? 0)
}

/**
 * The nav body shared by the desktop rail and the mobile drawer.
 * `collapsed` renders an icon-only rail; the mobile drawer is always expanded.
 */
function SidebarBody({
  collapsed,
  onNavigate,
  rail = false,
}: {
  collapsed: boolean
  onNavigate?: () => void
  /** In the desktop rail the open page's item is a tab joined to the page. */
  rail?: boolean
}) {
  const { user, logout } = useAuth()
  const router = useRouter()
  const isActive = useIsActive()
  const t = useTranslations('nav')
  const dueToday = useDueToday()

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
        aria-label="StudyFlow"
        className={cn(
          'flex h-11 items-center rounded-lg px-3 transition-colors hover:bg-slate-200/50',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-mode-library/40',
          collapsed && 'justify-center px-0',
        )}
        title={collapsed ? 'StudyFlow' : undefined}
      >
        <Wordmark compact={collapsed} />
      </Link>

      <nav className="mt-4 flex-1 space-y-1">
        {navItems.map((item) => {
          const active = isActive(item.href)
          const Icon = item.icon
          const due = item.label === 'home' && dueToday > 0 ? dueToday : 0
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              title={collapsed ? t(item.label) : undefined}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'relative flex h-11 items-center gap-3 px-3 text-[15px] transition-[background-color,color,box-shadow] duration-200 ease-out motion-reduce:transition-none',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-mode-library/40',
                active
                  ? cn('font-semibold', item.ink,
                      // The open page's tab: page-coloured paper that runs over
                      // the rail's edge into the page, like a bookmark in a book.
                      rail
                        ? 'z-10 -mr-[13px] rounded-l-lg bg-[#f8fafc] shadow-[0_1px_2px_rgb(15_23_42/0.06),-2px_2px_8px_-2px_rgb(15_23_42/0.10)]'
                        : 'rounded-lg bg-slate-100')
                  : 'rounded-lg font-medium text-slate-700 hover:bg-slate-200/60 hover:text-slate-900',
                collapsed && 'justify-center px-0',
              )}
            >
              <span
                className={cn(
                  'grid size-7 shrink-0 place-items-center rounded-md transition-colors duration-200 motion-reduce:transition-none',
                  active ? cn(item.tile, 'text-white') : 'text-current',
                )}
              >
                <Icon className="size-[18px]" strokeWidth={active ? 2.25 : 2} aria-hidden />
              </span>
              {!collapsed && <span className="truncate">{t(item.label)}</span>}
              {due > 0 && (
                <span
                  className={cn(
                    'rounded-[5px] bg-amber-100 px-1.5 font-mono text-xs font-medium tabular-nums text-amber-900',
                    collapsed ? 'absolute right-1 top-0.5 px-1 text-[10px]' : 'ml-auto',
                  )}
                >
                  {due > 99 ? '99+' : due}
                  <span className="sr-only"> {t('dueToday', { count: due })}</span>
                </span>
              )}
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
        <Link
          href="/dashboard/account"
          title={collapsed ? t('account') : undefined}
          className={cn(
            'flex h-10 w-full items-center gap-3 rounded-lg px-3 text-[15px] font-medium transition-colors',
            isActive('/dashboard/account')
              ? 'bg-slate-100 text-slate-900'
              : 'text-slate-700 hover:bg-slate-200/60 hover:text-slate-900',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-slate-400/40',
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
            'text-slate-700 hover:bg-red-50 hover:text-mode-danger',
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

// Hover intent: a pointer passing over the rail on its way somewhere does not
// open it, and one that slips off for a moment does not shut it.
const OPEN_DELAY_MS = 120
const CLOSE_DELAY_MS = 200

/** Persistent left rail on desktop: icons only, opening over the page while
 *  the pointer rests on it or the keyboard is inside it. The 68px it keeps in
 *  the layout never changes, so the page does not jump as it opens. */
export function AppSidebar() {
  const [open, setOpen] = useState(false)
  const timer = useRef<number | null>(null)

  const later = useCallback((next: boolean, ms: number) => {
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setOpen(next), ms)
  }, [])

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current)
  }, [])

  return (
    <div className="relative hidden w-[68px] shrink-0 md:block">
      <aside
        data-collapsed={!open}
        onMouseEnter={() => later(true, OPEN_DELAY_MS)}
        onMouseLeave={() => later(false, CLOSE_DELAY_MS)}
        onFocus={() => later(true, 0)}
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) later(false, 0)
        }}
        className={cn(
          'absolute inset-y-0 left-0 z-30 flex flex-col border-r border-slate-200 bg-[#edf1f5] p-3',
          'transition-[width,box-shadow] duration-200 ease-out motion-reduce:transition-none',
          open ? 'w-60 shadow-[8px_0_24px_-12px_rgb(15_23_42/0.25)]' : 'w-[68px]',
        )}
      >
        <SidebarBody collapsed={!open} rail />
      </aside>
    </div>
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
          <Wordmark className="text-lg" />
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
