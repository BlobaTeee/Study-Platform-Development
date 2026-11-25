'use client'

import { useId, useState } from 'react'
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

/** "Cần ôn": one line per notebook, closed until pressed. Opened, it is split
 *  by kind (wrong questions, forgotten cards, mix-ups, practice errors), each
 *  kind with its own heading and one action for all of it; a row opens to
 *  show an example and what to do about that one thing. */
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
          {nb.owed > 0 && nb.notebookId != null && <OwedGroup notebookId={nb.notebookId} owed={nb.owed} />}
          {nb.forgotten && <ForgottenGroup forgotten={nb.forgotten} />}
          {nb.mixUps.length > 0 && nb.notebookId != null && <MixUpGroup notebookId={nb.notebookId} items={nb.mixUps} />}
          {nb.practice && <PracticeGroup practice={nb.practice} />}
        </ul>
      )}
    </li>
  )
}

/** One kind of thing to review: a heading with how many, the one action that
 *  covers all of it (when there is one), and its rows underneath. */
function Group({ title, count, note, action, children }: {
  title: string
  count: number
  /** Where the items come from, when the title alone does not say. */
  note?: string
  action?: React.ReactNode
  children?: React.ReactNode
}) {
  return (
    <li className="py-4">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-900">
            {title}{' '}
            <span className="ml-1 font-mono text-xs font-normal tabular-nums text-slate-500">{count}</span>
          </h3>
          {note && <p className="text-xs text-slate-500">{note}</p>}
        </div>
        {action}
      </div>
      {children}
    </li>
  )
}

function Rows({ children }: { children: React.ReactNode }) {
  return <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">{children}</ul>
}

/** One row of a group: a name and a count, closed until pressed. Opened, it
 *  shows an example and what can be done about it. */
function Row({ label, meta, children }: { label: React.ReactNode; meta?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={id}
        className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
      >
        <ChevronDown
          className={cn('size-3.5 shrink-0 text-slate-400 transition-transform duration-200 motion-reduce:transition-none', !open && '-rotate-90')}
          aria-hidden
        />
        <span className="min-w-0 flex-1 truncate text-base text-slate-900">{label}</span>
        {meta && <span className="shrink-0 text-sm text-slate-600">{meta}</span>}
      </button>
      {open && (
        <div id={id} className="space-y-2 px-3 pb-3 pl-8">
          {children}
        </div>
      )}
    </li>
  )
}

function Actions({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2">{children}</div>
}

/** The mistake bank: one button to sit it again, then the concepts it groups
 *  into. Naming those concepts can take an AI request, so they are only
 *  fetched once the notebook is opened. */
function OwedGroup({ notebookId, owed }: { notebookId: number; owed: number }) {
  const t = useTranslations('analytics')
  const tests = useTranslations('tests')
  const router = useRouter()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')
  const { data, isLoading } = useSWR(['/quizzes/weak-concepts', notebookId], () => mockTestsAPI.weakConcepts(notebookId))
  const concepts: WeakConcept[] = data?.data?.concepts ?? []
  const found = useInPageLanguage(concepts.flatMap((c) => [c.label, c.sample[0]]))

  // Missed questions are redone like a quiz, marked one by one, not sat
  // as a timed paper.
  const retake = () => router.push(`/dashboard/quizzes/redo?notebook=${notebookId}`)

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
    <Group
      title={t('groupOwed')}
      count={owed}
      note={t('groupOwedFrom')}
      action={
        <Button variant="outline" size="sm" disabled={busy !== null} onClick={retake}>
          {t('retakeOwed')}
        </Button>
      }
    >
      {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
      {isLoading && <div className="mt-2 h-10 animate-pulse rounded-lg bg-slate-200/70 motion-reduce:animate-none" aria-busy />}
      {concepts.length > 0 && (
        <Rows>
          {concepts.map((c) => (
            <Row key={c.key} label={<InPageLanguage text={c.label} found={found} />} meta={t('weakMissed', { count: c.count })}>
              {c.sample[0] && (
                <p className="text-sm text-slate-600">
                  {t('forgottenSample', { question: shownAs(found, c.sample[0]) ?? c.sample[0] })}
                </p>
              )}
              <Actions>
                <Button variant="outline" size="sm" disabled={busy !== null} onClick={() => void practise(c)}>
                  {busy === c.key ? <Loader2 className="animate-spin" aria-hidden /> : null}
                  {busy === c.key ? tests('writingPractice') : c.practice_quiz_id ? tests('continuePractice') : tests('practise')}
                </Button>
              </Actions>
            </Row>
          ))}
        </Rows>
      )}
    </Group>
  )
}

// Enough groups to see what kind of thing is being forgotten; the rest wait
// behind a button so one notebook does not fill the page.
const FORGOTTEN_SHOWN = 3

function ForgottenGroup({ forgotten }: { forgotten: ForgottenNotebook }) {
  const t = useTranslations('analytics')
  const common = useTranslations('common')
  const [all, setAll] = useState(false)
  // Concept names and sample questions are in their documents' language.
  const found = useInPageLanguage(forgotten.groups.flatMap((g) => [g.label, g.sample]))
  const cardIds = [...new Set(forgotten.groups.flatMap((g) => g.card_ids))]
  const shown = all ? forgotten.groups : forgotten.groups.slice(0, FORGOTTEN_SHOWN)
  const extra = forgotten.groups.length - FORGOTTEN_SHOWN

  return (
    <Group
      title={t('groupForgotten')}
      count={forgotten.count}
      action={
        cardIds.length > 0 && (
          <Button asChild variant="outline" size="sm">
            <Link href={`/dashboard/flashcards?cards=${cardIds.join(',')}`}>{t('relearnAll', { count: cardIds.length })}</Link>
          </Button>
        )
      }
    >
      {shown.length > 0 && (
        <Rows>
          {shown.map((g) => (
            <Row key={g.key} label={<InPageLanguage text={g.label} found={found} />} meta={common('cards', { count: g.count })}>
              <p className="text-sm text-slate-600">
                {t('forgottenSample', { question: shownAs(found, g.sample) ?? g.sample })}
              </p>
              <Actions>
                <Button asChild variant="outline" size="sm">
                  <Link href={`/dashboard/flashcards?cards=${g.card_ids.join(',')}`}>{t('relearnGroup')}</Link>
                </Button>
                <Button asChild variant="ghost" size="sm">
                  <Link href={`/dashboard/explain?cards=${g.card_ids.join(',')}&concept=${encodeURIComponent(g.label)}`}>
                    {t('explainGroup')}
                  </Link>
                </Button>
              </Actions>
            </Row>
          ))}
        </Rows>
      )}
      {extra > 0 && (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          aria-expanded={all}
          className="mt-2 text-sm font-medium text-mode-ink underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
        >
          {all ? t('fewerGroups') : t('moreGroups', { count: extra })}
        </button>
      )}
    </Group>
  )
}

/** Two ideas the student keeps confusing; the button makes contrast cards
 *  for them once and opens them. */
function MixUpGroup({ notebookId, items }: { notebookId: number; items: Misconception[] }) {
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
    <Group title={t('groupMixUp')} count={items.length}>
      {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
      <Rows>
        {items.map((item) => (
          <Row
            key={item.key}
            label={t.rich('mixUpPair', {
              a: withOriginal(found, item.confused, item.difference || undefined),
              b: withOriginal(found, item.with, item.difference || undefined),
              strong: (chunk) => <span className="font-semibold">{chunk}</span>,
            })}
          >
            {item.difference && (
              <p className="text-sm text-slate-600">
                <InPageLanguage text={item.difference} found={found} />
              </p>
            )}
            <Actions>
              <Button variant="outline" size="sm" disabled={busy !== null} onClick={() => void practise(item.key)}>
                {busy === item.key ? <Loader2 className="animate-spin" aria-hidden /> : null}
                {t('contrastCards')}
              </Button>
            </Actions>
          </Row>
        ))}
      </Rows>
    </Group>
  )
}

/** Errors in practice problems, by kind; each opens the latest problem it was made in. */
function PracticeGroup({ practice: p }: { practice: PracticeMistakes }) {
  const t = useTranslations('analytics')
  const practice = useTranslations('practice')
  return (
    <Group title={t('groupPractice')} count={p.total}>
      <Rows>
        {p.types.map((k) => (
          <Row key={k.type} label={practice(`error_${k.type}`)} meta={practice('mistakeCount', { count: k.count })}>
            <Actions>
              <Button asChild variant="outline" size="sm">
                <Link href={`/dashboard/practice/${k.exercise_ids[k.exercise_ids.length - 1]}`}>{t('openProblem')}</Link>
              </Button>
            </Actions>
          </Row>
        ))}
      </Rows>
    </Group>
  )
}
