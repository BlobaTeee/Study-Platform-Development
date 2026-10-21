'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { Loader2 } from 'lucide-react'
import { exercisesAPI, type ExerciseSummary } from '@/lib/api'
import { toRedo } from '@/lib/practice'
import { cn } from '@/lib/utils'

type Mode = 'flashcards' | 'quizzes'
type Kind = 'cards' | 'quiz' | 'practice'

/** What to do with one document, as three index cards on a desk: the deck,
 *  the quiz and the practice problems. The card worth doing next sits
 *  forward with a tab, so the page says where to go without a banner. Each
 *  card has one main action and, where it makes sense, a quieter one
 *  (make again / make more). */
export function StudyDesk({
  notebookId,
  sourceId,
  disabled,
  cards,
  quiz,
}: {
  notebookId: number
  sourceId: number
  disabled: boolean
  cards: { count: number; toDo: number; studyHref: string; busy: boolean; onMake: () => void }
  quiz: { href: string | null; busy: boolean; onMake: () => void }
}) {
  const t = useTranslations('desk')
  const router = useRouter()
  const { data, mutate } = useSWR(['/exercises', 'source', sourceId], () => exercisesAPI.list({ source: sourceId }))
  const problems: ExerciseSummary[] = data?.data?.results ?? []
  const redo = toRedo(problems)
  const [making, setMaking] = useState(false)
  const [practiceError, setPracticeError] = useState<string | null>(null)

  const makeProblems = async () => {
    setMaking(true)
    setPracticeError(null)
    try {
      const res = await exercisesAPI.generate(sourceId)
      await mutate()
      const first = res.data.results[0]
      if (problems.length === 0 && first) router.push(`/dashboard/practice/${first.id}`)
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      setPracticeError(typeof detail === 'string' ? detail : t('makeFailed'))
    } finally {
      setMaking(false)
    }
  }

  // The card worth doing next: finish the deck, then test it, then apply it.
  const next: Kind =
    cards.count === 0 || cards.toDo > 0 ? 'cards'
      : !quiz.href ? 'quiz'
        : problems.length === 0 || redo > 0 ? 'practice'
          : 'quiz'

  const partWay = cards.toDo > 0 && cards.toDo < cards.count

  return (
    <section aria-labelledby="study-desk-heading" className="border-t border-slate-200 pt-5">
      <h3 id="study-desk-heading" className="font-display text-lg font-semibold text-slate-900">{t('title')}</h3>
      <ul className="-mx-1 mt-1 flex snap-x gap-4 overflow-x-auto px-1 pb-4 pt-8 md:grid md:grid-cols-3 md:overflow-visible">
        <IndexCard
          mode="flashcards"
          tilt={-0.6}
          next={next === 'cards'}
          label={t('cards')}
          headline={cards.count === 0 ? t('noCards') : t('cardCount', { count: cards.count })}
          detail={cards.count === 0 ? t('cardsLead') : cards.toDo > 0 ? t('cardsToDo', { count: cards.toDo }) : t('cardsDone')}
          primary={
            cards.count === 0
              ? { kind: 'button', label: t('makeCards'), onClick: cards.onMake, busy: cards.busy, disabled }
              : { kind: 'link', label: partWay ? t('continueCards') : cards.toDo > 0 ? t('studyCards') : t('reviewCards'), href: cards.studyHref }
          }
          secondary={cards.count > 0 ? { label: t('remake'), onClick: cards.onMake, busy: cards.busy, disabled } : undefined}
        />
        <IndexCard
          mode="quizzes"
          tilt={0.5}
          next={next === 'quiz'}
          label={t('quiz')}
          headline={quiz.href ? t('quizReady') : t('noQuiz')}
          detail={quiz.href ? t('quizLead') : t('quizMakeLead')}
          primary={
            quiz.href
              ? { kind: 'link', label: t('takeQuiz'), href: quiz.href }
              : { kind: 'button', label: t('makeQuiz'), onClick: quiz.onMake, busy: quiz.busy, disabled }
          }
          secondary={quiz.href ? { label: t('remake'), onClick: quiz.onMake, busy: quiz.busy, disabled } : undefined}
        />
        <IndexCard
          mode="quizzes"
          tilt={-0.3}
          next={next === 'practice'}
          label={t('practice')}
          headline={problems.length === 0 ? t('noProblems') : t('problemCount', { count: problems.length })}
          detail={problems.length === 0 ? t('practiceLead') : redo > 0 ? t('toRedo', { count: redo }) : t('practiceStepByStep')}
          primary={
            problems.length === 0
              ? { kind: 'button', label: t('makeProblems'), onClick: () => void makeProblems(), busy: making, disabled }
              : { kind: 'link', label: t('openProblems'), href: `/dashboard/practice?notebook=${notebookId}` }
          }
          secondary={problems.length > 0 ? { label: t('makeMore'), onClick: () => void makeProblems(), busy: making, disabled } : undefined}
          error={practiceError}
        />
      </ul>
    </section>
  )
}

type Primary =
  | { kind: 'link'; label: string; href: string }
  | { kind: 'button'; label: string; onClick: () => void; busy: boolean; disabled: boolean }

/** One index card: ruled lines, a margin rule under the header, a slight
 *  tilt as if laid on the desk. Text sits in slate-700 or darker so it
 *  reads on the ruling. */
function IndexCard({
  mode, tilt, next, label, headline, detail, primary, secondary, error,
}: {
  mode: Mode
  tilt: number
  next: boolean
  label: string
  headline: string
  detail: string
  primary: Primary
  secondary?: { label: string; onClick: () => void; busy: boolean; disabled: boolean }
  error?: string | null
}) {
  const t = useTranslations('desk')
  const action =
    'rounded-sm font-semibold text-mode-ink underline decoration-[1.5px] underline-offset-4 hover:decoration-2 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30'
  return (
    <li
      data-mode={mode}
      style={{ '--tilt': `${tilt}deg` } as React.CSSProperties}
      className={cn(
        'index-card relative flex min-h-[10.5rem] w-[13.75rem] shrink-0 snap-start flex-col rounded-md px-4 pb-3.5 pt-3 md:w-auto',
        'rotate-[var(--tilt)] transition-[transform,box-shadow] duration-200 ease-out motion-reduce:transition-none',
        'hover:rotate-0 motion-reduce:hover:rotate-[var(--tilt)]',
        next
          ? 'index-card-front -translate-y-1.5 hover:-translate-y-2 motion-reduce:hover:-translate-y-1.5'
          : 'index-card-rest hover:-translate-y-0.5 motion-reduce:hover:translate-y-0'
      )}
    >
      {next && (
        <span className="absolute -top-[1.15rem] right-3 rounded-t-md bg-mode-strong px-2 pb-0.5 pt-0.5 text-xs font-semibold text-mode-on">
          {t('next')}
        </span>
      )}
      <p className="text-[13px] font-semibold leading-[1.375rem] text-mode-ink">{label}</p>
      <p className="mt-3 font-display text-[17px] font-semibold leading-[1.625rem] text-slate-900">{headline}</p>
      <p className="text-[13.5px] leading-[1.625rem] text-slate-700">{detail}</p>
      <div className="mt-auto flex flex-wrap items-baseline gap-x-2 pt-3 text-sm">
        {primary.kind === 'link' ? (
          <Link href={primary.href} className={action}>{primary.label}</Link>
        ) : (
          <button type="button" onClick={primary.onClick} disabled={primary.disabled || primary.busy} className={cn(action, 'inline-flex items-center gap-1.5 disabled:cursor-not-allowed disabled:opacity-60')}>
            {primary.busy && <Loader2 className="size-3.5 animate-spin motion-reduce:animate-none" aria-hidden />}
            {primary.label}
          </button>
        )}
        {secondary && (
          <button
            type="button"
            onClick={secondary.onClick}
            disabled={secondary.disabled || secondary.busy}
            className="inline-flex items-center gap-1 rounded-sm text-[13px] text-slate-700 underline-offset-4 hover:text-slate-900 hover:underline focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span aria-hidden>·</span>
            {secondary.busy && <Loader2 className="size-3 animate-spin motion-reduce:animate-none" aria-hidden />}
            {secondary.label}
          </button>
        )}
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}
    </li>
  )
}
