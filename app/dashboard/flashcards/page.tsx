'use client'

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import useSWR from 'swr'
import { analyticsAPI, flashcardsAPI, type ReviewGrade } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useTranslations } from 'next-intl'
import { SourceContextBanner } from '@/components/source-context-banner'
import { useConfirm } from '@/components/confirm-dialog'
import { PageHeader } from '@/components/page-header'
import { AskTutor } from '@/components/ask-tutor'
import { SourceRequired } from '@/components/source-required'
import {
  hasAllSources,
  parseSourceIdsParam,
} from '@/lib/source-utils'
import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  Pencil,
  RotateCcw,
  Trash2,
} from 'lucide-react'

type Flashcard = {
  id: number
  question: string
  answer: string
  difficulty: string
  source_ids?: number[]
  /** Days until this card's notebook's test, when that is this week. */
  exam_in_days?: number | null
}

/** The three SM-2 grades, worst recall first. Only you can judge whether you
 *  remembered a card, so grading is the one step that cannot be automated —
 *  the number keys mirror the on-screen order. */
const GRADES: { value: ReviewGrade; className: string }[] = [
  { value: 'hard', className: 'border-red-300 bg-red-50 text-red-900 hover:bg-red-100' },
  { value: 'good', className: 'border-sky-300 bg-sky-50 text-sky-900 hover:bg-sky-100' },
  { value: 'easy', className: 'border-emerald-300 bg-emerald-50 text-emerald-900 hover:bg-emerald-100' },
]

function FlashcardsStudy() {
  const t = useTranslations('flashcards')
  const common = useTranslations('common')
  const searchParams = useSearchParams()
  const sourceParam = searchParams.get('source')
  const sourceIds = useMemo(() => parseSourceIdsParam(sourceParam), [sourceParam])
  // Two ways to study, both legitimate: work through a document before an exam,
  // or clear what the schedule says is owed today.
  const dueMode = searchParams.get('due') === '1'

  // Scoped to a document, the server picks today's share from that document;
  // the key carries the scope so the two queues never share a cache entry.
  const { data, isLoading } = useSWR(
    dueMode
      ? sourceParam ? ['/flashcards/due', sourceParam] : ['/flashcards/due']
      : sourceParam ? ['/flashcards/', sourceParam] : null,
    () => (dueMode ? flashcardsAPI.getDueCards(sourceIds) : flashcardsAPI.getFlashcards())
  )
  // Whether debt is left once today's share is done. Same key as the dashboard,
  // so it is usually cached already; the number holds all day, since each
  // review lowers what is owed and what is left of the day alike.
  const { data: recsRes } = useSWR(dueMode && !sourceParam ? ['/analytics/recommendations'] : null, () =>
    analyticsAPI.getRecommendations()
  )
  const heldBack: number = recsRes?.data?.due?.later ?? 0

  const allCards: Flashcard[] = data?.data?.results ?? data?.data ?? []
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [saving, setSaving] = useState(false)
  const [graded, setGraded] = useState<Set<number>>(new Set())
  const [lastReview, setLastReview] = useState<{ label: string; interval: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  // The AI wrote these cards; the student is the editor. Edits and deletions
  // are applied on top of the fetched list rather than re-fetching, so the
  // deck order under the cursor does not change.
  const [edits, setEdits] = useState<Record<number, { question: string; answer: string }>>({})
  const [removed, setRemoved] = useState<Set<number>>(new Set())
  const [draft, setDraft] = useState<{ question: string; answer: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirm, confirmDialog] = useConfirm()

  const flashcards = useMemo(() => {
    const live = allCards
      .filter((f) => !removed.has(f.id))
      .map((f) => (edits[f.id] ? { ...f, ...edits[f.id] } : f))
    // The backend already picked the due cards; a source filter still applies if
    // one is present. Grading a card settles its debt, so it leaves the queue —
    // otherwise wrapping round would review it twice and corrupt its schedule.
    if (dueMode) {
      const scoped = sourceIds.length
        ? live.filter((f) => hasAllSources(f.source_ids, sourceIds))
        : live
      return scoped.filter((f) => !graded.has(f.id))
    }
    if (sourceIds.length === 0) return []
    return live.filter((f) => hasAllSources(f.source_ids, sourceIds))
  }, [allCards, sourceIds, dueMode, graded, edits, removed])

  const total = flashcards.length

  // The due queue shrinks under the cursor; fall back to the top of what's left.
  useEffect(() => {
    if (index >= total && total > 0) setIndex(0)
  }, [index, total])

  const goPrev = useCallback(() => {
    setFlipped(false)
    setIndex((i) => (i > 0 ? i - 1 : total - 1))
  }, [total])

  const goNext = useCallback(() => {
    setFlipped(false)
    setIndex((i) => (i < total - 1 ? i + 1 : 0))
  }, [total])

  const grade = useCallback(
    async (value: ReviewGrade) => {
      const card = flashcards[index]
      if (!card || saving) return
      setSaving(true)
      setError(null)
      try {
        const res = await flashcardsAPI.recordReview(card.id, value)
        setLastReview({
          label: t(value),
          interval: res.data.interval,
        })
        setGraded((g) => new Set(g).add(card.id))
        // In due mode the card drops out of the queue and the next one slides
        // into this slot, so only the browse mode needs to advance.
        if (dueMode) setFlipped(false)
        else goNext()
      } catch {
        // Stay on the card so the grade isn't silently lost.
        setError(t('saveFailed'))
      } finally {
        setSaving(false)
      }
    },
    [flashcards, index, saving, goNext, dueMode]
  )

  // Keyboard: space/enter flips, arrows move, number keys grade a revealed
  // card — the range comes from GRADES.length so removing/adding a grade
  // renumbers the shortcuts automatically instead of drifting out of sync.
  useEffect(() => {
    if (total === 0 || draft) return  // typing in the editor must not flip or grade
    const onKey = (e: KeyboardEvent) => {
      // Any field on the page (the tutor's question box, say) keeps its
      // keys: a space there is a space, a "2" is a "2".
      if (isTypingTarget(e.target)) return
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        setFlipped((f) => !f)
      } else if (e.key === 'ArrowRight') {
        goNext()
      } else if (e.key === 'ArrowLeft') {
        goPrev()
      } else if (flipped && /^[1-9]$/.test(e.key) && Number(e.key) <= GRADES.length) {
        e.preventDefault()
        grade(GRADES[Number(e.key) - 1].value)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [total, goNext, goPrev, flipped, grade, draft])

  const saveEdit = async (card: Flashcard) => {
    if (!draft) return
    const question = draft.question.trim()
    const answer = draft.answer.trim()
    if (!question || !answer) {
      setError(t('bothSidesRequired'))
      return
    }
    setBusy(true)
    setError(null)
    try {
      await flashcardsAPI.updateFlashcard(card.id, { question, answer })
      setEdits((e) => ({ ...e, [card.id]: { question, answer } }))
      setDraft(null)
    } catch {
      setError(t('saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  const deleteCard = async (card: Flashcard) => {
    const ok = await confirm({
      title: t('deleteTitle'),
      body: t('deleteBody'),
      confirmLabel: common('delete'),
      cancelLabel: common('cancel'),
    })
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      await flashcardsAPI.deleteFlashcard(card.id)
      setRemoved((r) => new Set(r).add(card.id))
      setFlipped(false)
      // The next card slides into this slot; only clamp if this was the last.
      setIndex((i) => (i >= total - 1 ? 0 : i))
    } catch {
      setError(t('deleteFailed'))
    } finally {
      setBusy(false)
    }
  }

  // Studying the due queue needs no document chosen — the schedule already knows.
  if (!dueMode && (!sourceParam || sourceIds.length === 0)) {
    return <SourceRequired type="flashcards" />
  }

  if (isLoading) {
    return <p className="py-20 text-center text-base text-slate-500">{common('loading')}</p>
  }

  if (total === 0) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title={dueMode ? t('dueToday') : t('studySession')} />
        <div className="sheet mt-8 flex flex-col items-start gap-5 p-8">
        <p className="max-w-[48ch] text-lg leading-relaxed text-slate-700">
          {dueMode
            ? graded.size > 0
              ? t(heldBack > 0 ? 'doneForTodayReviewed' : 'caughtUpReviewed', {
                  cards: common('cards', { count: graded.size }),
                })
              : t('nothingDue')
            : t('noneForSelection')}
        </p>
        {/* Studying a document enters the scheduled queue, so "nothing due" is
            the common landing. Offering the whole document here keeps that an
            answer rather than a dead end, while still leading with the
            schedule — reviewing early is a choice, not the default. */}
        {dueMode && sourceParam ? (
          <div className="flex flex-wrap gap-3">
            <Button asChild variant="outline">
              <Link href={`/dashboard/flashcards?source=${sourceParam}`}>{t('studyAllAnyway')}</Link>
            </Button>
            <Button asChild variant="ink">
              <Link href="/dashboard/notebooks">{t('backToNotebooks')}</Link>
            </Button>
          </div>
        ) : (
          <Button asChild variant="ink">
            <Link href={dueMode ? '/dashboard/analytics' : '/dashboard/notebooks'}>
              {dueMode ? t('backToProgress') : t('goToNotebooks')}
            </Link>
          </Button>
        )}
        </div>
      </div>
    )
  }

  // The clamping effect above runs after this render, so on the frame a graded
  // card leaves the queue the index can still point past the end.
  const card = flashcards[index] ?? flashcards[0]

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <Suspense fallback={null}>
        <SourceContextBanner />
      </Suspense>

      <PageHeader
        title={dueMode ? t('dueToday') : t('studySession')}
        meta={dueMode ? t('leftAndDone', { left: total, done: graded.size }) : `${index + 1} / ${total}`}
        action={
          <Button asChild variant="outline">
            <Link href={dueMode ? '/dashboard/analytics' : '/dashboard/notebooks'}>
              <ChevronLeft aria-hidden />
              {dueMode ? t('progress') : t('backToNotebooks')}
            </Link>
          </Button>
        }
      />

      <div className="h-1 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={Math.round(dueMode ? (graded.size / (graded.size + total)) * 100 : ((index + 1) / total) * 100)}>
        <div
          className="h-full bg-mode transition-[width] duration-300 motion-reduce:transition-none"
          style={{
            // Browsing tracks position in the deck; the due queue tracks the
            // debt cleared, since its cards leave as they are graded.
            width: dueMode
              ? `${(graded.size / (graded.size + total)) * 100}%`
              : `${((index + 1) / total) * 100}%`,
          }}
        />
      </div>

      {/* Why this card is ahead of older debt: its notebook's test is close. */}
      {dueMode && card?.exam_in_days != null && (
        <p className="-mt-4 text-sm text-slate-600">{t('examSoon', { days: card.exam_in_days })}</p>
      )}

      {/* Signature: a real index card that flips in 3D. */}
      {draft ? (
        <form
          className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sheet md:p-8"
          onSubmit={(e) => {
            e.preventDefault()
            void saveEdit(card)
          }}
        >
          <label className="block space-y-1.5">
            <span className="font-mono text-sm font-semibold uppercase tracking-wide text-mode-flashcards">{t('question')}</span>
            <textarea
              value={draft.question}
              onChange={(e) => setDraft({ ...draft, question: e.target.value })}
              rows={3}
              autoFocus
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-lg text-slate-900 outline-none focus-visible:border-mode-flashcards focus-visible:ring-mode-flashcards/25 focus-visible:ring-[4px]"
            />
          </label>
          <label className="block space-y-1.5">
            <span className="font-mono text-sm font-semibold uppercase tracking-wide text-slate-500">{t('answer')}</span>
            <textarea
              value={draft.answer}
              onChange={(e) => setDraft({ ...draft, answer: e.target.value })}
              rows={4}
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-lg text-slate-900 outline-none focus-visible:border-mode-flashcards focus-visible:ring-mode-flashcards/25 focus-visible:ring-[4px]"
            />
          </label>
          <div className="flex flex-wrap justify-end gap-3">
            <Button type="button" variant="outline" disabled={busy} onClick={() => setDraft(null)}>
              {common('cancel')}
            </Button>
            <Button type="submit" disabled={busy}>
              {common('save')}
            </Button>
          </div>
        </form>
      ) : (
      <div className="flip-scene">
        <button
          type="button"
          onClick={() => setFlipped((f) => !f)}
          aria-label={flipped ? t('showQuestion') : t('showAnswer')}
          aria-pressed={flipped}
          className="group block w-full text-left rounded-2xl outline-none focus-visible:ring-4 focus-visible:ring-mode-flashcards/30"
        >
          <div
            className={cn(
              'flip-card min-h-[340px] md:min-h-[400px]',
              flipped && 'is-flipped'
            )}
          >
            <IndexFace side="front" card={card} />
            <IndexFace side="back" card={card} />
          </div>
        </button>
      </div>
      )}

      {/* Once the answer is showing, grading replaces navigation: the only
          question left is how well you recalled it. */}
      {flipped ? (
        <div className="space-y-3">
          <p className="text-center text-sm text-slate-600">{t('howWell')}</p>
          <div className="grid grid-cols-3 gap-3">
            {GRADES.map((g, i) => (
              <button
                key={g.value}
                type="button"
                disabled={saving}
                onClick={() => grade(g.value)}
                className={cn(
                  'rounded-xl border px-4 py-3 text-left transition-[background-color,transform] duration-150 active:translate-y-px disabled:opacity-50',
                  'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30',
                  g.className
                )}
              >
                <span className="flex items-baseline justify-between gap-2">
                  <span className="text-base font-semibold">{t(g.value)}</span>
                  <kbd className="font-mono text-xs opacity-70 tabular-nums">{i + 1}</kbd>
                </span>
                <span className="block text-sm opacity-80">{t(`${g.value}Hint`)}</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Button variant="outline" size="lg" onClick={goPrev}>
            <ArrowLeft aria-hidden />
            {t('previous')}
          </Button>
          <Button size="lg" onClick={() => setFlipped(true)} className="px-8">
            <RotateCcw aria-hidden />
            {t('showAnswer')}
          </Button>
          <Button variant="outline" size="lg" onClick={goNext}>
            {t('skip')}
            <ArrowRight aria-hidden />
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" className="text-center text-sm text-red-700">
          {error}
        </p>
      )}

      {/* The tutor: only with the answer showing, and never while editing.
          Keyed by card so a new card starts a new, empty thread. */}
      {flipped && !draft && <AskTutor key={card.id} cardId={card.id} />}

      {/* Quiet on purpose: fixing a card is the exception, recalling it the rule. */}
      {!draft && (
        <div className="flex justify-center gap-5 text-sm text-slate-600">
          <button
            type="button"
            disabled={busy}
            onClick={() => setDraft({ question: card.question, answer: card.answer })}
            className="inline-flex items-center gap-1.5 hover:text-slate-900 disabled:opacity-50"
          >
            <Pencil className="size-3.5" aria-hidden />
            {t('editCard')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void deleteCard(card)}
            className="inline-flex items-center gap-1.5 hover:text-red-700 disabled:opacity-50"
          >
            <Trash2 className="size-3.5" aria-hidden />
            {t('deleteCard')}
          </button>
        </div>
      )}
      {confirmDialog}

      <p className="text-center text-sm text-slate-500">
        {lastReview
          ? t('lastReview', { grade: lastReview.label, days: lastReview.interval, graded: graded.size, total })
          : t('hint', { difficulty: difficultyLabel(card.difficulty, t) })}
      </p>
    </div>
  )
}

/** True when the key event comes from somewhere the user is typing. */
function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

/** One face of the index card. The tabbed top edge and ruled baseline are
 *  the physical cues; front is amber (prompt), back is ink (recall). */
function IndexFace({ side, card }: { side: 'front' | 'back'; card: Flashcard }) {
  const t = useTranslations('flashcards')
  const isFront = side === 'front'
  return (
    <div
      className={cn(
        'flip-face relative flex flex-col justify-center rounded-2xl border border-slate-200 bg-white p-8 shadow-sheet md:p-12',
        isFront ? 'flip-face--front' : 'flip-face--back'
      )}
    >
      {/* Binder tab on the top edge, colored to the card's role */}
      <span
        className={cn(
          'absolute left-8 -top-px h-[3px] w-14 rounded-b-full',
          isFront ? 'bg-mode' : 'bg-slate-900'
        )}
        aria-hidden
      />
      <p
        className={cn(
          'mb-5 text-sm font-medium',
          isFront ? 'text-mode' : 'text-slate-500'
        )}
      >
        {isFront ? t('question') : t('answer')}
      </p>
      <p className="text-2xl leading-relaxed text-slate-900 md:text-[1.75rem] text-pretty">
        {isFront ? card.question : card.answer}
      </p>
      {/* Ruled baseline — a single notebook rule under the content */}
      <span className="mt-8 block h-px w-full bg-slate-100" aria-hidden />
    </div>
  )
}

export default function FlashcardsPage() {
  return (
    <Suspense fallback={<p className="text-xl text-slate-500 py-20 text-center">Loading…</p>}>
      <FlashcardsStudy />
    </Suspense>
  )
}

function difficultyLabel(difficulty: string, t: (key: string) => string): string {
  if (difficulty === 'easy') return t('difficultyEasy')
  if (difficulty === 'hard') return t('difficultyHard')
  return t('difficultyMedium')
}
