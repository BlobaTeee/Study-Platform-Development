'use client'

import { useAuth } from '@/lib/auth-context'
import { useRouter, usePathname } from 'next/navigation'
import { useEffect } from 'react'
import { cn } from '@/lib/utils'
import { authAPI } from '@/lib/api'
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

  if (loading) {
    return (
      <div className="paper-grid flex h-screen flex-col items-center justify-center gap-4">
        <div className="size-9 animate-spin rounded-full border-4 border-slate-200 border-t-mode-library" />
        <p className="font-mono text-xs uppercase tracking-[0.14em] text-slate-500">Loading</p>
      </div>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden bg-white text-slate-900">
      <AppSidebar />

      <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col">
        <MobileNavBar />

        <main className="paper-grid min-h-0 flex-1 overflow-auto">
          <div className={cn('h-full w-full', isNotebooks ? 'p-0' : 'mx-auto max-w-6xl p-6 md:p-10')}>
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
