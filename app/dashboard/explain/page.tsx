'use client'

import { Suspense, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { BookOpen, Check, ChevronLeft, CircleAlert, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/page-header'
import { explainAPI, type FeynmanFeedback } from '@/lib/api'
import { parseSourceIdsParam } from '@/lib/source-utils'
import { cn } from '@/lib/utils'

/** Must match MIN_CHARS in backend/study_sessions/feynman.py. */
const MIN_CHARS = 20

/** The Feynman technique on a group of forgotten cards: explain the idea as
 *  if teaching it, then read what was right, what is missing and what is
 *  wrong. The cards themselves stay out of sight — seeing them first would
 *  turn explaining into copying. */
function ExplainConcept() {
  const t = useTranslations('explain')
  const common = useTranslations('common')
  const searchParams = useSearchParams()
  const cardsParam = searchParams.get('cards')
  const cardIds = useMemo(() => parseSourceIdsParam(cardsParam), [cardsParam])
  const concept = searchParams.get('concept')?.trim() || t('thisIdea')

  const { data: latestRes, isLoading, mutate } = useSWR(
    cardIds.length ? ['/study/explain', cardsParam] : null,
    () => explainAPI.latest(cardIds)
  )
  const latest = latestRes?.data && 'id' in latestRes.data ? (latestRes.data as FeynmanFeedback) : null

  // The draft starts from the last attempt, so "try again" means improving
  // what was written rather than starting over.
  const [draft, setDraft] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const text = draft ?? latest?.text ?? ''
  const showFeedback = latest && !editing

  const submit = async () => {
    if (text.trim().length < MIN_CHARS || sending) return
    setSending(true)
    setError(null)
    try {
      const res = await explainAPI.submit({ card_ids: cardIds, concept, text: text.trim() })
      await mutate({ ...latestRes!, data: res.data }, { revalidate: false })
      setDraft(null)
      setEditing(false)
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      setError(typeof detail === 'string' ? detail : t('failed'))
    } finally {
      setSending(false)
    }
  }

  const back = (
    <Button asChild variant="outline">
      <Link href="/dashboard/analytics">
        <ChevronLeft aria-hidden />
        {t('backToProgress')}
      </Link>
    </Button>
  )

  if (cardIds.length === 0) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title={t('title')} action={back} />
        <p className="sheet mt-8 p-8 text-lg text-slate-700">{t('noCards')}</p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <PageHeader title={t('title')} action={back} />

      <section className="sheet p-6 md:p-8" aria-labelledby="concept-title">
        <p className="text-sm font-medium text-mode-ink">{t('concept')}</p>
        <h2 id="concept-title" className="mt-1 font-display text-2xl text-slate-900 text-balance md:text-3xl">
          {concept}
        </h2>

        {isLoading ? (
          <div className="mt-6 h-40 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none" aria-busy />
        ) : showFeedback ? (
          <div className="mt-6">
            <p className="text-sm font-medium text-slate-600">{t('youWrote')}</p>
            <p className="mt-1 max-w-[65ch] whitespace-pre-line text-base leading-relaxed text-slate-700">{latest.text}</p>
          </div>
        ) : (
          <form
            className="mt-6 space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              void submit()
            }}
          >
            <label htmlFor="explanation" className="block max-w-[65ch] text-base leading-relaxed text-slate-700">
              {t('prompt')}
            </label>
            <textarea
              id="explanation"
              autoFocus
              rows={7}
              value={text}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={t('placeholder')}
              className="block w-full resize-y rounded-lg border border-slate-300 bg-white px-4 py-3 text-base leading-relaxed text-slate-900 placeholder:text-slate-500 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-slate-600">{t('hint')}</p>
              <div className="ml-auto flex gap-2">
                {latest && (
                  <Button type="button" variant="outline" onClick={() => setEditing(false)} disabled={sending}>
                    {common('cancel')}
                  </Button>
                )}
                <Button type="submit" disabled={sending || text.trim().length < MIN_CHARS}>
                  {sending ? t('reading') : t('submit')}
                </Button>
              </div>
            </div>
            {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          </form>
        )}
      </section>

      {showFeedback && (
        <Feedback
          feedback={latest}
          onRetry={() => {
            setDraft(latest.text)
            setEditing(true)
          }}
        />
      )}
    </div>
  )
}

function Feedback({ feedback, onRetry }: { feedback: FeynmanFeedback; onRetry: () => void }) {
  const t = useTranslations('explain')
  return (
    <section className="sheet divide-y divide-slate-200" aria-label={t('feedback')} aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-4 p-6 md:p-8">
        <p className="max-w-[48ch] text-lg leading-relaxed text-slate-900">{t(`level_${feedback.level}`)}</p>
        <Button variant="tinted" onClick={onRetry}>{t('retry')}</Button>
      </div>

      <Points title={t('correct')} items={feedback.correct} icon={<Check className="size-4 text-emerald-700" aria-hidden />} />
      <Points title={t('missing')} items={feedback.missing} icon={<Plus className="size-4 text-amber-700" aria-hidden />} />

      {feedback.wrong.length > 0 && (
        <div className="p-6 md:p-8">
          <h3 className="text-base font-semibold text-slate-900">{t('wrong')}</h3>
          <ul className="mt-3 space-y-4">
            {feedback.wrong.map((w, i) => (
              <li key={i} className="flex gap-3">
                <CircleAlert className="mt-1 size-4 shrink-0 text-red-700" aria-hidden />
                <div className="max-w-[65ch] text-base leading-relaxed">
                  <p className="text-slate-700">{t('youSaid', { claim: w.claim })}</p>
                  <p className="text-slate-900">{t('actually', { correction: w.correction })}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {feedback.reread.length > 0 && (
        <div className="p-6 md:p-8">
          <h3 className="text-base font-semibold text-slate-900">{t('reread')}</h3>
          <div className="mt-3 space-y-3">
            {feedback.reread.map((p) => (
              <Passage key={`${p.source_id}-${p.passage.slice(0, 40)}`} passage={p} />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function Points({ title, items, icon }: { title: string; items: string[]; icon: React.ReactNode }) {
  if (items.length === 0) return null
  return (
    <div className="p-6 md:p-8">
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      <ul className="mt-3 space-y-2">
        {items.map((item, i) => (
          <li key={i} className="flex max-w-[65ch] gap-3 text-base leading-relaxed text-slate-800">
            <span className="mt-1 shrink-0">{icon}</span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Passage({ passage }: { passage: FeynmanFeedback['reread'][number] }) {
  const t = useTranslations('explain')
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-medium text-slate-600">
          <BookOpen className="size-3.5" aria-hidden />
          {passage.title}
        </p>
        <Link
          href={`/dashboard/notebooks/${passage.notebook_id}?source=${passage.source_id}`}
          className="text-sm font-medium text-mode-library hover:underline"
        >
          {t('openDocument')} →
        </Link>
      </div>
      <p className={cn('mt-2 max-w-[70ch] text-sm leading-relaxed text-slate-700', !open && 'line-clamp-4')}>
        {passage.passage}
      </p>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mt-1 text-xs text-slate-600 underline underline-offset-4 hover:text-slate-900"
      >
        {open ? t('showLess') : t('showMore')}
      </button>
    </div>
  )
}

export default function ExplainPage() {
  return (
    <Suspense fallback={null}>
      <ExplainConcept />
    </Suspense>
  )
}
