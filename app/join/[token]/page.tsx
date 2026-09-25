'use client'

import { use, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { mutate } from 'swr'
import { notebooksAPI } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { Button } from '@/components/ui/button'
import { AuthBrandPanel } from '@/components/auth-brand-panel'
import { LanguageSwitch } from '@/components/language-switch'

type Joined = { id: number; title: string }

/** Where an invitation link lands. Signed in, it redeems the token and says
 *  which notebook you joined; signed out, it sends you to log in and comes
 *  back here afterwards. */
export default function JoinPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params)
  const t = useTranslations('notebooks')
  const router = useRouter()
  const { user, loading } = useAuth()
  const [joined, setJoined] = useState<Joined | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (loading || !user || joined) return
    let cancelled = false
    notebooksAPI
      .acceptInvite(token)
      .then((res) => {
        if (cancelled) return
        setJoined(res.data.notebook)
        mutate(['/notebooks/'])          // the new notebook belongs in the list
      })
      .catch((err) => {
        if (cancelled) return
        const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        setError(detail || t('joinFailed'))
      })
    return () => {
      cancelled = true
    }
  }, [loading, user, token, joined, t])

  return (
    <main className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      <AuthBrandPanel />

      <section className="flex items-center justify-center bg-white px-6 py-14">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-start justify-between gap-4">
            <h1 className="font-display text-3xl font-semibold text-slate-900 lg:hidden">StudyFlow</h1>
            <div className="ml-auto">
              <LanguageSwitch />
            </div>
          </div>

          <h2 className="font-display text-[2rem] font-semibold leading-tight text-slate-900">
            {joined ? t('joinedTitle') : t('joinTitle')}
          </h2>

          {loading ? (
            <p className="mt-3 text-base text-slate-600">{t('joining')}</p>
          ) : !user ? (
            <div className="mt-3 space-y-6">
              <p className="text-base text-slate-600">{t('joinSignedOut')}</p>
              <Button size="lg" className="w-full" onClick={() => router.push(`/login?next=/join/${token}`)}>
                {t('joinTitle')}
              </Button>
            </div>
          ) : error ? (
            <div className="mt-3 space-y-6">
              <p className="text-base text-red-700">{error}</p>
              <Button asChild variant="outline" size="lg" className="w-full">
                <Link href="/dashboard/notebooks">{t('allNotebooks')}</Link>
              </Button>
            </div>
          ) : joined ? (
            <div className="mt-3 space-y-6">
              <p className="text-base text-slate-600">{t('joinedBody', { title: joined.title })}</p>
              <Button asChild size="lg" className="w-full">
                <Link href={`/dashboard/notebooks/${joined.id}`}>{t('openNotebook')}</Link>
              </Button>
            </div>
          ) : (
            <p className="mt-3 text-base text-slate-600">{t('joining')}</p>
          )}
        </div>
      </section>
    </main>
  )
}
