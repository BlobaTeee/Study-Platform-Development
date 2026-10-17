'use client'

import { ChatLauncher } from '@/components/chat-launcher'
import { useAuth } from '@/lib/auth-context'
import { useRouter, usePathname } from 'next/navigation'
import { useEffect } from 'react'
import { cn } from '@/lib/utils'
import { authAPI } from '@/lib/api'
import { isLocale, readLocaleCookie, writeLocaleCookie } from '@/i18n/locale'
import { AppSidebar, MobileNavBar } from '@/components/dashboard-sidebar'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { user, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  // Notebook surfaces manage their own full-height layout and padding.
  const isNotebooks = pathname?.startsWith('/dashboard/notebooks')
  // The section's colour, read by buttons, focus rings and the page rule.
  const mode = modeFor(pathname ?? '')

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login')
    }
  }, [user, loading, router])

  // Tell the API which clock this student reads, so reminder emails state
  // the test time in it rather than in the server's zone. Once per browser
  // session: the zone does not change under a running tab, and a PUT on
  // every navigation would be noise. Failure is silent — the profile keeps
  // its previous zone and the next session tries again.
  useEffect(() => {
    if (!user) return
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone
    if (!zone) return
    const key = `tz-synced:${user.id}:${zone}`
    try {
      if (sessionStorage.getItem(key)) return
    } catch {
      /* private mode: just sync every load */
    }
    authAPI
      .updateProfile({ timezone: zone })
      .then(() => {
        try {
          sessionStorage.setItem(key, '1')
        } catch {
          /* ignore */
        }
      })
      .catch(() => {})
  }, [user])

  // Language: the cookie is the truth on this browser, the profile is the
  // memory across browsers. On sign-in, a choice already made here (the
  // switch on the login page) is pushed up to the account; a browser with no
  // choice yet adopts the account's. Either way the two end up agreeing.
  useEffect(() => {
    if (!user) return
    const chosenHere = readLocaleCookie()
    authAPI
      .getProfile()
      .then((res) => {
        const preferred = res.data?.preferred_language
        if (chosenHere) {
          if (preferred !== chosenHere) {
            authAPI.updateProfile({ preferred_language: chosenHere }).catch(() => {})
          }
        } else if (isLocale(preferred)) {
          writeLocaleCookie(preferred)
          router.refresh()
        }
      })
      .catch(() => {})
  }, [user, router])

  if (loading) {
    return (
      <div className="paper-grid flex h-screen flex-col items-center justify-center gap-4">
        <div className="size-8 animate-spin rounded-full border-[3px] border-slate-200 border-t-mode-library motion-reduce:animate-none" />
      </div>
    )
  }

  return (
    <div data-mode={mode} className="flex h-screen overflow-hidden bg-white text-slate-900">
      <AppSidebar />

      <ChatLauncher />

      <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col">
        <MobileNavBar />

        <main className="paper-grid min-h-0 flex-1 overflow-auto">
          <div className={cn('h-full w-full', isNotebooks ? 'p-0' : 'mx-auto max-w-5xl px-4 py-6 md:px-10 md:py-10')}>
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}

/** Which of the four colourways a route belongs to. Home and account are ink. */
function modeFor(pathname: string): 'library' | 'flashcards' | 'quizzes' | 'analytics' | 'ink' {
  if (pathname.startsWith('/dashboard/notebooks')) return 'library'
  // Explaining a concept starts from forgotten cards, so it wears their colour.
  if (pathname.startsWith('/dashboard/flashcards') || pathname.startsWith('/dashboard/explain')) return 'flashcards'
  if (pathname.startsWith('/dashboard/quizzes') || pathname.startsWith('/dashboard/tests') ||
      pathname.startsWith('/dashboard/practice')) return 'quizzes'
  if (pathname.startsWith('/dashboard/analytics')) return 'analytics'
  return 'ink'
}
