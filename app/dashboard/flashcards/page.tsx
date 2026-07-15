'use client'

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import useSWR from 'swr'
import { flashcardsAPI, type ReviewGrade } from '@/lib/api'
import { cn } from '@/lib/utils'
import { SourceContextBanner } from '@/components/source-context-banner'
import { SourceRequired } from '@/components/source-required'
import {
  flashcardMatchesSourceTag,
  parseSourceIdsParam,
} from '@/lib/source-utils'
import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  RotateCcw,
  Zap,
} from 'lucide-react'

type Flashcard = {
  id: number
  question: string
  answer: string
  difficulty: string
  tags?: string | null
}

/** The four SM-2 grades, worst recall first. Only you can judge whether you
 *  remembered a card, so grading is the one step that cannot be automated —
 *  the number keys mirror the on-screen order. */
const GRADES: { value: ReviewGrade; label: string; hint: string; className: string }[] = [
  { value: 'again', label: 'Again', hint: 'Forgot', className: 'border-red-300 bg-red-50 text-red-900 hover:bg-red-100' },
  { value: 'hard', label: 'Hard', hint: 'Struggled', className: 'border-orange-300 bg-orange-50 text-orange-900 hover:bg-orange-100' },
  { value: 'good', label: 'Good', hint: 'Recalled', className: 'border-sky-300 bg-sky-50 text-sky-900 hover:bg-sky-100' },
  { value: 'easy', label: 'Easy', hint: 'Instantly', className: 'border-emerald-300 bg-emerald-50 text-emerald-900 hover:bg-emerald-100' },
]

function FlashcardsStudy() {
  const searchParams = useSearchParams()
  const sourceParam = searchParams.get('source')
  const sourceIds = useMemo(() => parseSourceIdsParam(sourceParam), [sourceParam])
  // Two ways to study, both legitimate: work through a document before an exam,
  // or clear what the schedule says is owed today.
  const dueMode = searchParams.get('due') === '1'

  const { data, isLoading } = useSWR(
    dueMode ? ['/flashcards/due'] : sourceParam ? ['/flashcards/', sourceParam] : null,
    () => (dueMode ? flashcardsAPI.getDueCards() : flashcardsAPI.getFlashcards())
  )

  const allCards: Flashcard[] = data?.data?.results ?? data?.data ?? []
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [saving, setSaving] = useState(false)
  const [graded, setGraded] = useState<Set<number>>(new Set())
  const [lastReview, setLastReview] = useState<{ label: string; interval: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const flashcards = useMemo(() => {
    // The backend already picked the due cards; a source filter still applies if
    // one is present. Grading a card settles its debt, so it leaves the queue —
    // otherwise wrapping round would review it twice and corrupt its schedule.
    if (dueMode) {
      const scoped = sourceIds.length
        ? allCards.filter((f) => flashcardMatchesSourceTag(f.tags, sourceIds))
        : allCards
      return scoped.filter((f) => !graded.has(f.id))
    }
    if (sourceIds.length === 0) return []
    return allCards.filter((f) => flashcardMatchesSourceTag(f.tags, sourceIds))
  }, [allCards, sourceIds, dueMode, graded])

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
          label: GRADES.find((g) => g.value === value)!.label,
          interval: res.data.interval,
        })
        setGraded((g) => new Set(g).add(card.id))
        // In due mode the card drops out of the queue and the next one slides
        // into this slot, so only the browse mode needs to advance.
        if (dueMode) setFlipped(false)
        else goNext()
      } catch {
        // Stay on the card so the grade isn't silently lost.
        setError('Could not save that review. Is the backend running?')
      } finally {
        setSaving(false)
      }
    },
    [flashcards, index, saving, goNext, dueMode]
  )

  // Keyboard: space/enter flips, arrows move, 1-4 grade a revealed card.
  useEffect(() => {
    if (total === 0) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        setFlipped((f) => !f)
      } else if (e.key === 'ArrowRight') {
        goNext()
      } else if (e.key === 'ArrowLeft') {
        goPrev()
      } else if (flipped && /^[1-4]$/.test(e.key)) {
        e.preventDefault()
        grade(GRADES[Number(e.key) - 1].value)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [total, goNext, goPrev, flipped, grade])

  // Studying the due queue needs no document chosen — the schedule already knows.
  if (!dueMode && (!sourceParam || sourceIds.length === 0)) {
    return <SourceRequired type="flashcards" />
  }

  if (isLoading) {
    return <p className="text-xl text-slate-500 text-center py-20">Loading flashcards…</p>
  }

  if (total === 0) {
    return (
      <div className="text-center py-20 max-w-md mx-auto">
        <Zap className="size-16 text-slate-300 mx-auto mb-4" />
        <p className="text-xl text-slate-600 mb-6">
          {dueMode
            ? graded.size > 0
              ? `Caught up — ${graded.size} card${graded.size === 1 ? '' : 's'} reviewed. Nothing else is due.`
              : 'Nothing due right now. Cards come back as their dates arrive.'
            : 'No flashcards for this selection yet.'}
        </p>
        <Button asChild size="lg" className="bg-mode-library hover:bg-mode-library-hover h-12 text-lg">
          <Link href={dueMode ? '/dashboard/analytics' : '/dashboard/notebooks'}>
            {dueMode ? 'Back to progress' : 'Go to Notebooks'}
          </Link>
        </Button>
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

      <div className="rise border-t-[3px] border-mode-flashcards pt-4 flex items-center justify-between gap-4">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-flashcards">
            Flashcards
          </p>
          <h1 className="font-display text-3xl font-semibold text-slate-900 mt-1">
            {dueMode ? 'Due today' : 'Study session'}
          </h1>
          <p className="font-mono text-sm text-slate-500 mt-1 tabular-nums">
            {dueMode
              ? `${total} left${graded.size > 0 ? ` · ${graded.size} done` : ''}`
              : `${String(index + 1).padStart(2, '0')} / ${String(total).padStart(2, '0')}`}
          </p>
        </div>
        <Button asChild variant="outline" size="lg" className="text-lg h-11">
          <Link href={dueMode ? '/dashboard/analytics' : '/dashboard/notebooks'}>
            <ChevronLeft className="size-5 mr-1" />
            {dueMode ? 'Progress' : 'Notebooks'}
          </Link>
        </Button>
      </div>

      <div className="rise h-1.5 rounded-full bg-slate-100 overflow-hidden" style={{ animationDelay: '60ms' }}>
        <div
          className="h-full bg-mode-flashcards transition-all duration-300"
          style={{
            // Browsing tracks position in the deck; the due queue tracks the
            // debt cleared, since its cards leave as they are graded.
            width: dueMode
              ? `${(graded.size / (graded.size + total)) * 100}%`
              : `${((index + 1) / total) * 100}%`,
          }}
        />
      </div>

      {/* Signature: a real index card that flips in 3D. */}
      <div className="rise flip-scene" style={{ animationDelay: '120ms' }}>
        <button
          type="button"
          onClick={() => setFlipped((f) => !f)}
          aria-label={flipped ? 'Show question' : 'Show answer'}
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

      {/* Once the answer is showing, grading replaces navigation: the only
          question left is how well you recalled it. */}
      {flipped ? (
        <div className="rise space-y-3" style={{ animationDelay: '180ms' }}>
          <p className="text-center text-sm text-slate-500">How well did you recall it?</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {GRADES.map((g, i) => (
              <button
                key={g.value}
                type="button"
                disabled={saving}
                onClick={() => grade(g.value)}
                className={cn(
                  'rounded-xl border-2 px-4 py-3 text-left transition-colors disabled:opacity-50',
                  g.className
                )}
              >
                <span className="flex items-baseline justify-between gap-2">
                  <span className="text-lg font-semibold">{g.label}</span>
                  <span className="font-mono text-xs opacity-60 tabular-nums">{i + 1}</span>
                </span>
                <span className="block text-sm opacity-75">{g.hint}</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="rise flex flex-wrap items-center justify-center gap-4" style={{ animationDelay: '180ms' }}>
          <Button variant="outline" size="lg" onClick={goPrev} className="h-12 px-6 text-lg">
            <ArrowLeft className="size-5 mr-2" />
            Previous
          </Button>
          <Button
            size="lg"
            onClick={() => setFlipped(true)}
            className="bg-mode-flashcards hover:bg-mode-flashcards-hover text-white h-12 px-6 text-lg"
          >
            <RotateCcw className="size-5 mr-2" />
            Show answer
          </Button>
          <Button variant="outline" size="lg" onClick={goNext} className="h-12 px-6 text-lg">
            Skip
            <ArrowRight className="size-5 ml-2" />
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" className="rise text-center text-sm text-red-700">
          {error}
        </p>
      )}

      <p className="rise text-center font-mono text-xs uppercase tracking-wide text-slate-500" style={{ animationDelay: '220ms' }}>
        {lastReview
          ? `${lastReview.label} · back in ${lastReview.interval} day${lastReview.interval === 1 ? '' : 's'} · ${graded.size}/${total} graded`
          : `Space to flip · 1-4 to grade · difficulty: ${card.difficulty}`}
      </p>
    </div>
  )
}

/** One face of the index card. The tabbed top edge and ruled baseline are
 *  the physical cues; front is amber (prompt), back is ink (recall). */
function IndexFace({ side, card }: { side: 'front' | 'back'; card: Flashcard }) {
  const isFront = side === 'front'
  return (
    <div
      className={cn(
        'flip-face relative flex flex-col justify-center rounded-2xl border border-slate-200 bg-white p-8 md:p-12 shadow-sheet',
        isFront ? 'flip-face--front' : 'flip-face--back'
      )}
    >
      {/* Binder tab on the top edge, colored to the card's role */}
      <span
        className={cn(
          'absolute left-8 -top-px h-[3px] w-14 rounded-b-full',
          isFront ? 'bg-mode-flashcards' : 'bg-slate-900'
        )}
        aria-hidden
      />
      <p
        className={cn(
          'font-mono text-sm font-semibold uppercase tracking-wide mb-5',
          isFront ? 'text-mode-flashcards' : 'text-slate-500'
        )}
      >
        {isFront ? 'Question' : 'Answer'}
      </p>
      <p className="text-2xl md:text-3xl text-slate-900 leading-relaxed">
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
