'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { useAuth } from '@/lib/auth-context'

/** How long to wait for a session the URL promised before giving up on it. */
const CONFIRM_TIMEOUT_MS = 10_000

/** True when we arrived here from an email link (confirmation, magic link,
 *  OAuth). supabase-js reads those parameters and stores the session
 *  asynchronously, so the landing must not be redirected away first. */
function landedFromAuthLink(): boolean {
  if (typeof window === 'undefined') return false
  const hash = window.location.hash
  return (
    hash.includes('access_token') ||
    hash.includes('error') ||
    new URLSearchParams(window.location.search).has('code')
  )
}

export default function Page() {
  const { user, loading } = useAuth()
  const router = useRouter()
  // Read once, on mount: supabase-js clears the hash as soon as it has read it.
  const [confirming, setConfirming] = useState(landedFromAuthLink)
  const t = useTranslations('auth')

  // A link that never resolves into a session must not hang here for ever.
  useEffect(() => {
    if (!confirming) return
    const timer = window.setTimeout(() => setConfirming(false), CONFIRM_TIMEOUT_MS)
    return () => window.clearTimeout(timer)
  }, [confirming])

  useEffect(() => {
    if (user) {
      router.replace('/dashboard/notebooks')
      return
    }
    // Only send someone to sign in once there is nothing left to wait for.
    if (!loading && !confirming) {
      router.replace('/login')
    }
  }, [user, loading, confirming, router])

  return (
    <main className="flex min-h-screen items-center justify-center bg-white">
      <div className="text-center">
        <div className="mb-4 animate-spin motion-reduce:animate-none">
          <div className="mx-auto size-10 rounded-full border-4 border-slate-200 border-t-mode-library" />
        </div>
        <p className="text-slate-600">{confirming ? t('confirmingAccount') : t('loadingApp')}</p>
      </div>
    </main>
  )
}
