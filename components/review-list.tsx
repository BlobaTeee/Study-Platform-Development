'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import useSWR from 'swr'
import { ChevronDown, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  mockTestsAPI,
  reviewsAPI,
  type ForgottenNotebook,
  type Misconception,
  type PracticeMistakes,
  type WeakConcept,
} from '@/lib/api'
import { reviewSize, type ReviewNotebook } from '@/lib/review-list'
import { type Ask, shownAs, withOriginal } from '@/lib/translate'
import { InPageLanguage, useInPageLanguage } from '@/components/in-page-language'
import { cn } from '@/lib/utils'

type Entry = ReviewNotebook<ForgottenNotebook, Misconception, PracticeMistakes>

// A sitting of the mistake bank started from here gets the setup form's default.
const RETAKE_MINUTES = 30

/** "Cần ôn": one line per notebook, closed until pressed. Opened, every item
 *  says where it comes from and has one way to work on it. */
export function ReviewList({ notebooks }: { notebooks: Entry[] }) {
  const [open, setOpen] = useState<Set<string>>(new Set())
  const toggle = (key: string) =>
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  return (
    <ul className="mt-3 divide-y divide-slate-200 rounded-xl border border-slate-200">
      {notebooks.map((nb) => (
        <ReviewNotebookRow key={nb.key} nb={nb} isOpen={open.has(nb.key)} onToggle={() => toggle(nb.key)} />
      ))}
    </ul>
  )
}

function ReviewNotebookRow({ nb, isOpen, onToggle }: { nb: Entry; isOpen: boolean; onToggle: () => void }) {
  const t = useTranslations('analytics')
  const common = useTranslations('common')
  const practice = useTranslations('practice')
  const panelId = `review-${nb.key}`
  const title = nb.key === 'own' ? practice('mistakesOwn') : nb.title || t('untitledNotebook')

  const parts: string[] = []
  if (nb.owed) parts.push(t('reviewOwedPart', { count: nb.owed }))
  if (nb.forgotten) parts.push(common('cards', { count: nb.forgotten.count }))
  if (nb.mixUps.length) parts.push(t('reviewMixUpPart', { count: nb.mixUps.length }))
  if (nb.practice) parts.push(t('reviewPracticePart', { count: nb.practice.total }))

  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        aria-controls={panelId}
        className="flex w-full items-center gap-2 rounded-xl p-3 text-left hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 sm:p-4"
      >
        <ChevronDown
          className={cn(
            'size-4 shrink-0 text-slate-500 transition-transform duration-200 motion-reduce:transition-none',
            !isOpen && '-rotate-90'
          )}
          aria-hidden
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-base font-medium text-slate-900">{title}</span>
          <span className="block text-sm text-slate-600">{parts.join(' · ')}</span>
        </span>
        <span className="font-mono text-sm tabular-nums text-slate-500">{reviewSize(nb)}</span>
      </button>
      {isOpen && (
        <ul id={panelId} className="divide-y divide-slate-100 border-t border-slate-100 bg-slate-50/60 px-3 sm:px-4">
          {nb.owed > 0 && nb.notebookId != null && <OwedItems notebookId={nb.notebookId} owed={nb.owed} />}
          {nb.forgotten && <ForgottenItems forgotten={nb.forgotten} />}
          {nb.mixUps.length > 0 && nb.notebookId != null && <MixUpItems notebookId={nb.notebookId} items={nb.mixUps} />}
          {nb.practice && <PracticeItems practice={nb.practice} />}
        </ul>
      )}
    </li>
  )
}

/** One item: where it comes from, what it is, and what to do about it. */
function Item({ tag, children, actions }: { tag: string; children: React.ReactNode; actions: React.ReactNode }) {
  return (
    <li className="flex flex-col items-start gap-2 py-3 sm:flex-row sm:items-center sm:gap-4">
      <span className="w-20 shrink-0 text-xs font-medium uppercase tracking-wide text-slate-500">{tag}</span>
      <div className="min-w-0 w-full flex-1">{children}</div>
      <div className="flex shrink-0 flex-wrap items-center gap-1 sm:gap-2">{actions}</div>
    </li>
  )
}

/** The mistake bank: one line to sit it again, then the concepts it groups
 *  into. Naming those concepts can take an AI request, so they are only
 *  fetched once the notebook is opened. */
function OwedItems({ notebookId, owed }: { notebookId: number; owed: number }) {
  const t = useTranslations('analytics')
  const tests = useTranslations('tests')
  const router = useRouter()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')
  const { data, isLoading } = useSWR(['/quizzes/weak-concepts', notebookId], () => mockTestsAPI.weakConcepts(notebookId))
  const concepts: WeakConcept[] = data?.data?.concepts ?? []
  const found = useInPageLanguage(concepts.flatMap((c) => [c.label, c.sample[0]]))

  const retake = async () => {
    setBusy('retake')
    setError('')
    try {
      const res = await mockTestsAPI.start({ notebook: notebookId, duration_minutes: RETAKE_MINUTES, mistakes_only: true })
      router.push(`/dashboard/tests?id=${res.data.id}`)
    } catch {
      setError(tests('startFailed'))
      setBusy(null)
    }
  }

  const practise = async (c: WeakConcept) => {
    setBusy(c.key)
    setError('')
    try {
      const res = await mockTestsAPI.practiceConcept({ notebook: notebookId, question_ids: c.question_ids, label: c.label, key: c.key })
      router.push(`/dashboard/quizzes?source=${res.data.source_ids.join(',')}&quiz=${res.data.quiz_id}`)
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail || tests('practiceFailed'))
      setBusy(null)
    }
  }

  return (
    <>
      <Item
        tag={t('tagOwed')}
        actions={
          <Button variant="outline" size="sm" disabled={busy !== null} onClick={() => void retake()}>
            {busy === 'retake' ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t('retakeOwed')}
          </Button>
        }
      >
        <p className="text-base text-slate-900">{t('owedLine', { count: owed })}</p>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      </Item>
      {isLoading && (
        <li className="py-3">
          <div className="h-5 w-56 animate-pulse rounded bg-slate-200/70 motion-reduce:animate-none" aria-busy />
        </li>
      )}
      {concepts.map((c) => (
        <Item
          key={c.key}
          tag={t('tagWeak')}
          actions={
            <Button variant="outline" size="sm" disabled={busy !== null} onClick={() => void practise(c)}>
              {busy === c.key ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {busy === c.key ? tests('writingPractice') : c.practice_quiz_id ? tests('continuePractice') : tests('practise')}
            </Button>
          }
        >
          <p className="text-base text-slate-900">
            <InPageLanguage text={c.label} found={found} />
            <span className="ml-2 text-sm text-slate-600">{t('weakMissed', { count: c.count })}</span>
          </p>
          {c.sample[0] && (
            <p className="line-clamp-1 text-sm text-slate-600">
              <InPageLanguage text={c.sample[0]} found={found} />
            </p>
          )}
        </Item>
      ))}
    </>
  )
}

function ForgottenItems({ forgotten }: { forgotten: ForgottenNotebook }) {
  const t = useTranslations('analytics')
  const common = useTranslations('common')
  // Concept names and sample questions are in their documents' language.
  const found = useInPageLanguage(forgotten.groups.flatMap((g) => [g.label, g.sample]))
  return (
    <>
      {forgotten.groups.map((g) => (
        <Item
          key={g.key}
          tag={t('tagForgotten')}
          actions={
            <>
              <Button asChild variant="outline" size="sm">
                <Link href={`/dashboard/flashcards?cards=${g.card_ids.join(',')}`}>{t('relearnGroup')}</Link>
              </Button>
              <Button asChild variant="ghost" size="sm" className="px-2 sm:px-3">
                <Link href={`/dashboard/explain?cards=${g.card_ids.join(',')}&concept=${encodeURIComponent(g.label)}`}>
                  {t('explainGroup')}
                </Link>
              </Button>
            </>
          }
        >
          <p className="text-base text-slate-900">
            <InPageLanguage text={g.label} found={found} />
            <span className="ml-2 text-sm text-slate-600">{common('cards', { count: g.count })}</span>
          </p>
          <p className="line-clamp-1 text-sm text-slate-600">
            {t('forgottenSample', { question: shownAs(found, g.sample) ?? g.sample })}
          </p>
        </Item>
      ))}
    </>
  )
}

/** Two ideas the student keeps confusing; the button makes contrast cards
 *  for them once and opens them. */
function MixUpItems({ notebookId, items }: { notebookId: number; items: Misconception[] }) {
  const t = useTranslations('analytics')
  const router = useRouter()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')
  const found = useInPageLanguage(items.flatMap((item): Ask[] => [
    ...[item.confused, item.with].map((w) => (item.difference ? { text: w, context: item.difference } : w)),
    item.difference,
  ]))

  const practise = async (key: string) => {
    setBusy(key)
    setError('')
    try {
      const res = await reviewsAPI.practiseMisconception(notebookId, key)
      router.push(`/dashboard/flashcards?cards=${res.data.card_ids.join(',')}`)
    } catch {
      setError(t('misconceptionFailed'))
      setBusy(null)
    }
  }

  return (
    <>
      {items.map((item) => (
        <Item
          key={item.key}
          tag={t('tagMixUp')}
          actions={
            <Button variant="outline" size="sm" disabled={busy !== null} onClick={() => void practise(item.key)}>
              {busy === item.key ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t('contrastCards')}
            </Button>
          }
        >
          <p className="text-base text-slate-900">
            {t.rich('mixUp', {
              a: withOriginal(found, item.confused, item.difference || undefined),
              b: withOriginal(found, item.with, item.difference || undefined),
              strong: (chunk) => <span className="font-semibold">{chunk}</span>,
            })}
          </p>
          {item.difference && (
            <p className="line-clamp-2 text-sm text-slate-600">
              <InPageLanguage text={item.difference} found={found} />
            </p>
          )}
          {error && busy === null && <p role="alert" className="text-sm text-red-700">{error}</p>}
        </Item>
      ))}
    </>
  )
}

/** Errors in practice problems, by kind; each opens the latest problem it was made in. */
function PracticeItems({ practice: p }: { practice: PracticeMistakes }) {
  const t = useTranslations('analytics')
  const practice = useTranslations('practice')
  return (
    <>
      {p.types.map((k) => (
        <Item
          key={k.type}
          tag={t('tagPractice')}
          actions={
            <Button asChild variant="outline" size="sm">
              <Link href={`/dashboard/practice/${k.exercise_ids[k.exercise_ids.length - 1]}`}>{t('openProblem')}</Link>
            </Button>
          }
        >
          <p className="text-base text-slate-900">
            {practice(`error_${k.type}`)}
            <span className="ml-2 text-sm text-slate-600">{practice('mistakeCount', { count: k.count })}</span>
          </p>
        </Item>
      ))}
    </>
  )
}
