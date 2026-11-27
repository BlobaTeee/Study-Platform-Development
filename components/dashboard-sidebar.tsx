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
function Wordmark({ compact = false, className, style }: { compact?: boolean; className?: string; style?: React.CSSProperties }) {
  if (compact) {
    return (
      <span className={cn('font-display text-2xl font-semibold italic leading-none text-mode-library-ink', className)} aria-hidden>
        S
      </span>
    )
  }
  return (
    <span className={cn('font-display text-xl font-semibold leading-tight text-slate-900', className)} style={style}>
      Study<span className="font-medium italic text-mode-library-ink">Flow</span>
    </span>
  )
}

/** Everything owed today, read from the same request as the home page:
 *  today's share of due cards, missed questions to redo, practice problems due. */
function useDueToday(): number {
  const { data } = useSWR(['/analytics/recommendations'], () => analyticsAPI.getRecommendations())
  const due = data?.data?.due
  const beyond = data?.data?.beyond_cards
  const cards = due ? due.today ?? (due.due ?? 0) + (due.new ?? 0) : 0
  return cards + (beyond?.owed ?? 0) + (beyond?.practice_due ?? 0)
}

// Opening glides out and settles (ease-out-expo); closing tucks away quickly.
const GLIDE_OUT = 'ease-[cubic-bezier(0.16,1,0.3,1)]'
const GLIDE_IN = 'ease-[cubic-bezier(0.5,0,0.75,0)]'

/** A label that is always there, so nothing reflows: it glides in from the
 *  icon's side when the rail opens, and is gone at once when it closes. */
function fade(hidden: boolean) {
  return cn(
    'whitespace-nowrap transition-[opacity,transform] motion-reduce:transition-none',
    hidden
      ? cn('pointer-events-none -translate-x-3 opacity-0 duration-100', GLIDE_IN)
      : cn('translate-x-0 opacity-100 duration-500', GLIDE_OUT),
  )
}

/** Each row a beat after the one above, so the words arrive as a wave down
 *  the rail rather than all at once. Leaving has no wave. */
function stagger(hidden: boolean, row: number): React.CSSProperties {
  return { transitionDelay: hidden ? '0ms' : `${70 + row * 28}ms` }
}

/**
 * The nav body shared by the desktop rail and the mobile drawer.
 * `collapsed` shows the icon-only rail. Every icon keeps its place in both
 * states (its centre sits on the rail's middle), so opening only adds words
 * beside the icons; nothing jumps. The mobile drawer is always expanded.
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
          'relative flex h-11 items-center overflow-hidden rounded-lg px-2 transition-colors hover:bg-slate-200/50',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-mode-library/40',
        )}
        title={collapsed ? 'StudyFlow' : undefined}
      >
        {/* The italic S on the rail becomes the whole name as it opens. */}
        <span
          className={cn(
            'absolute left-2 grid w-7 place-items-center transition-[opacity,transform] motion-reduce:transition-none',
            GLIDE_OUT,
            // Back only once the name has faded, so the two never overlap.
            collapsed ? 'scale-100 opacity-100 delay-150 duration-300' : 'scale-75 opacity-0 duration-100',
          )}
        >
          <Wordmark compact />
        </span>
        <Wordmark className={cn('inline-block pl-1', fade(collapsed))} style={stagger(collapsed, 0)} />
      </Link>

      <nav className="mt-4 flex-1 space-y-1">
        {navItems.map((item, row) => {
          const active = isActive(item.href)
          const Icon = item.icon
          const due = item.label === 'home' && dueToday > 0 ? dueToday : 0
          const count = due > 99 ? '99+' : due
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              title={collapsed ? t(item.label) : undefined}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'relative flex h-11 items-center gap-3 overflow-hidden px-2 text-[15px] transition-[background-color,color,box-shadow] duration-200 ease-out motion-reduce:transition-none',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-mode-library/40',
                active
                  ? cn('font-semibold', item.ink,
                      // The open page's tab: page-coloured paper that runs over
                      // the rail's edge into the page, like a bookmark in a book.
                      rail
                        ? 'z-10 -mr-[13px] rounded-l-lg bg-[#f8fafc] shadow-[0_1px_2px_rgb(15_23_42/0.06),-2px_2px_8px_-2px_rgb(15_23_42/0.10)]'
                        : 'rounded-lg bg-slate-100')
                  : 'rounded-lg font-medium text-slate-700 hover:bg-slate-200/60 hover:text-slate-900',
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
              <span className={cn('min-w-0 flex-1 truncate', fade(collapsed))} style={stagger(collapsed, row + 1)}>{t(item.label)}</span>
              {due > 0 && (
                <>
                  {/* On the rail the count sits on the icon's corner; open, it moves to the end of the row. */}
                  <span
                    aria-hidden
                    className={cn(
                      'absolute left-[26px] top-0.5 rounded-[5px] bg-amber-100 px-1 font-mono text-[10px] font-medium tabular-nums text-amber-900',
                      'transition-opacity motion-reduce:transition-none',
                      collapsed ? 'opacity-100 delay-150 duration-200' : 'opacity-0 duration-100',
                    )}
                  >
                    {count}
                  </span>
                  <span className={cn('rounded-[5px] bg-amber-100 px-1.5 font-mono text-xs font-medium tabular-nums text-amber-900', fade(collapsed))} style={stagger(collapsed, row + 2)}>
                    {count}
                    <span className="sr-only"> {t('dueToday', { count: due })}</span>
                  </span>
                </>
              )}
            </Link>
          )
        })}
      </nav>

      <div className="space-y-1 pt-4">
        {/* Two segments when there is room; on the icon-only rail, one square
            button showing the current code that switches on press — a reader
            who keeps the rail collapsed must still be able to find this. The
            one not in use is inert, so Tab never lands on something unseen. */}
        <div className="relative h-11">
          <div
            inert={!collapsed}
            className={cn('absolute left-0 top-0 transition-opacity motion-reduce:transition-none', collapsed ? 'opacity-100 delay-150 duration-200' : 'opacity-0 duration-100')}
          >
            <LanguageSwitch variant="toggle" />
          </div>
          <div inert={collapsed} className={cn('absolute left-1 top-1.5', fade(collapsed))} style={stagger(collapsed, 2)}>
            <LanguageSwitch compact />
          </div>
        </div>
        <Link
          href="/dashboard/account"
          title={collapsed ? t('account') : undefined}
          className={cn(
            'flex h-10 w-full items-center gap-3 overflow-hidden rounded-lg px-2 text-[15px] font-medium transition-colors',
            isActive('/dashboard/account')
              ? 'bg-slate-100 text-slate-900'
              : 'text-slate-700 hover:bg-slate-200/60 hover:text-slate-900',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-slate-400/40',
          )}
        >
          <span className="grid size-7 shrink-0 place-items-center">
            <UserRound className="size-[18px]" aria-hidden />
          </span>
          <span className={cn('truncate', fade(collapsed))} style={stagger(collapsed, 3)}>{user?.username ?? t('account')}</span>
        </Link>
        <button
          type="button"
          onClick={handleLogout}
          title={collapsed ? t('signOut') : undefined}
          className={cn(
            'flex h-10 w-full items-center gap-3 overflow-hidden rounded-lg px-2 text-[15px] font-medium transition-colors',
            'text-slate-700 hover:bg-red-50 hover:text-mode-danger',
            'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-red-500/25',
          )}
        >
          <span className="grid size-7 shrink-0 place-items-center">
            <LogOut className="size-[18px]" aria-hidden />
          </span>
          <span className={fade(collapsed)} style={stagger(collapsed, 4)}>{t('signOut')}</span>
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
 *  the layout never changes, so the page does not jump as it opens.
 *
 *  Nothing changes width. The 240px panel is uncovered by clips that grow
 *  from the rail's edge: one for the content, one for the paper under it,
 *  run on the same clock and curve so they cannot drift apart. Closed, the
 *  content's clip stops 13px past the rail, so the open page's bookmark tab
 *  still crosses into the page, while the paper stops at the rail's border.
 *  A clip also keeps the hidden part from catching the pointer. The shadow
 *  sits on a wrapper, so it follows the paper's clipped edge. */
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

  const motion = cn('motion-reduce:transition-none', open ? cn('duration-500', GLIDE_OUT) : cn('duration-300', GLIDE_IN))

  return (
    <aside
      data-collapsed={!open}
      onMouseEnter={() => later(true, OPEN_DELAY_MS)}
      onMouseLeave={() => later(false, CLOSE_DELAY_MS)}
      onFocus={() => later(true, 0)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) later(false, 0)
      }}
      className="relative z-30 hidden w-[68px] shrink-0 border-r border-slate-200 bg-[#edf1f5] md:block"
    >
      {/* The paper, and its shadow on a wrapper so the shadow follows the clipped edge. */}
      <div
        aria-hidden
        className={cn(
          'pointer-events-none absolute inset-y-0 left-0 w-60 transition-[filter]',
          motion,
          open ? '[filter:drop-shadow(10px_0_18px_rgb(15_23_42/0.16))]' : '[filter:drop-shadow(0_0_0_rgb(15_23_42/0))]',
        )}
      >
        <div
          className={cn(
            'absolute inset-0 border-r border-slate-200 bg-[#edf1f5] transition-[clip-path]',
            motion,
            open ? '[clip-path:inset(0_0_0_0)]' : '[clip-path:inset(0_173px_0_0)]',
          )}
        />
      </div>
      <div
        className={cn(
          'absolute inset-y-0 left-0 flex w-60 flex-col p-3 transition-[clip-path]',
          motion,
          open ? '[clip-path:inset(0_0_0_0)]' : '[clip-path:inset(0_159px_0_0)]',
        )}
      >
        <SidebarBody collapsed={!open} rail />
      </div>
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
