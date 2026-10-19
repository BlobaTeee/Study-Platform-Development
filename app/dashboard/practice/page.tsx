'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { ArrowRight, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/page-header'
import { exercisesAPI, type ExerciseSummary } from '@/lib/api'
import { cn } from '@/lib/utils'

/** Must match MIN_OWN_CHARS in backend/exercises/services/problems.py. */
const MIN_CHARS = 15

/** Practice on problems the student brings, on any subject. They belong to
 *  no notebook: they are graded from general knowledge, not from documents,
 *  so filing them under one would claim a link that is not there. */
export default function OwnPracticePage() {
  const t = useTranslations('practice')
  const router = useRouter()
  const { data, isLoading } = useSWR(['/exercises', 'own'], () => exercisesAPI.list({ own: 1 }))
  const problems: ExerciseSummary[] = [...(data?.data?.results ?? [])].reverse()   // newest first
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const create = async () => {
    if (text.trim().length < MIN_CHARS || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await exercisesAPI.own(text.trim())
      router.push(`/dashboard/practice/${res.data.id}`)
    } catch (e) {
      const body = (e as { response?: { data?: { detail?: unknown; incomplete?: boolean } } }).response?.data
      const detail = typeof body?.detail === 'string' ? body.detail : null
      setError(detail ? (body?.incomplete ? t('ownIncomplete', { missing: detail }) : detail) : t('failed'))
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <PageHeader title={t('ownTitle')} />

      <form
        className="sheet space-y-4 p-6 md:p-8"
        onSubmit={(e) => {
          e.preventDefault()
          void create()
        }}
      >
        <label htmlFor="own-problem" className="block max-w-[65ch] text-base leading-relaxed text-slate-700">
          {t('ownLead')}
        </label>
        <textarea
          id="own-problem"
          rows={6}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t('ownPlaceholder')}
          className="block w-full resize-y rounded-lg border border-slate-300 bg-white px-4 py-3 text-base leading-relaxed text-slate-900 placeholder:text-slate-500 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-[48ch] text-sm text-slate-600">{t('ownGeneralNote')}</p>
          <Button type="submit" disabled={busy || text.trim().length < MIN_CHARS}>
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {busy ? t('ownChecking') : t('ownSubmit')}
          </Button>
        </div>
        {error && <p role="alert" className="max-w-[65ch] text-sm text-red-700">{error}</p>}
      </form>

      <section className="sheet p-6 md:p-8" aria-labelledby="own-list-title">
        <h2 id="own-list-title" className="text-base font-semibold text-slate-900">{t('ownList')}</h2>
        {isLoading ? (
          <div className="mt-4 h-24 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none" aria-busy />
        ) : problems.length === 0 ? (
          <p className="mt-2 text-slate-600">{t('ownEmpty')}</p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-100">
            {problems.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/dashboard/practice/${p.id}`}
                  className="-mx-2 flex items-center gap-3 rounded-md px-2 py-3 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                >
                  <span className="w-10 shrink-0 text-xs text-slate-600">{t(`difficulty_${p.difficulty}`)}</span>
                  <span className="min-w-0 flex-1 truncate text-base text-slate-900">{p.prompt}</span>
                  <span
                    className={cn(
                      'shrink-0 text-xs',
                      p.status === 'mastered' ? 'text-emerald-700' : p.due ? 'font-medium text-mode-ink' : 'text-slate-600'
                    )}
                  >
                    {p.due ? t('dueAgain') : p.attempted ? t('status_started') : t(`status_${p.status}`)}
                  </span>
                  <ArrowRight className="size-3.5 shrink-0 text-slate-400" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
