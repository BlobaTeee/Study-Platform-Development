'use client'

import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import useSWR from 'swr'
import { quizzesAPI } from '@/lib/api'
import { parseSourceIdsParam, hasAllSources } from '@/lib/source-utils'
import { SourceContextBanner } from '@/components/source-context-banner'
import { SourceRequired } from '@/components/source-required'
import { ArrowRight, BookOpen, CheckCircle2, ChevronLeft, CircleDashed, Keyboard, XCircle } from 'lucide-react'

type Question = {
  id: number
  question_text: string
  question_type: string
  options: string[]
  correct_answer: string
  explanation?: string
  order: number
}

type Quiz = {
  id: number
  title: string
  description?: string
  source_ids?: number[]
  questions: Question[]
}

type Graded = {
  id: number
  verdict: 'correct' | 'near' | 'wrong'
  how: string
  is_correct: boolean
  reference_answer: string
  explanation?: string | null
}

const TYPED_MODE_KEY = 'quiz-typed-mode'

function QuizzesStudy() {
  const searchParams = useSearchParams()
  const sourceParam = searchParams.get('source')
  const sourceIds = useMemo(() => parseSourceIdsParam(sourceParam), [sourceParam])
  const quizIdParam = searchParams.get('quiz')

  const { data, isLoading } = useSWR(
    sourceParam ? ['/quizzes/', sourceParam] : null,
    () => quizzesAPI.getQuizzes()
  )

  const allQuizzes: Quiz[] = data?.data?.results ?? data?.data ?? []
  const quizzes = useMemo(() => {
    if (sourceIds.length === 0) return []
    return allQuizzes.filter((q) => hasAllSources(q.source_ids, sourceIds))
  }, [allQuizzes, sourceIds])

  const quiz = useMemo(() => {
    if (!quizzes.length) return null
    if (quizIdParam) {
      return quizzes.find((q) => q.id === Number(quizIdParam)) ?? quizzes[0]
    }
    return quizzes[0]
  }, [quizzes, quizIdParam])

  const questions = useMemo(
    () => [...(quiz?.questions ?? [])].sort((a, b) => a.order - b.order),
    [quiz]
  )

  const [qIndex, setQIndex] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const [score, setScore] = useState(0)
  const [finished, setFinished] = useState(false)
  const [attemptId, setAttemptId] = useState<number | null>(null)
  const [starting, setStarting] = useState(false)

  // Typed mode: recall instead of recognition. Off by default, remembered
  // per browser; a 503 from the grader (no model built) turns it off again.
  const [typedMode, setTypedMode] = useState(false)
  const [typedUnavailable, setTypedUnavailable] = useState(false)
  const [typed, setTyped] = useState('')
  const [grading, setGrading] = useState(false)
  const [graded, setGraded] = useState<Graded | null>(null)
  const [typedError, setTypedError] = useState('')

  useEffect(() => {
    try {
      setTypedMode(localStorage.getItem(TYPED_MODE_KEY) === '1')
    } catch {
      /* private mode: stays off */
    }
  }, [])

  const toggleTypedMode = () => {
    const next = !typedMode
    setTypedMode(next)
    try {
      localStorage.setItem(TYPED_MODE_KEY, next ? '1' : '0')
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    setQIndex(0)
    setSelected(null)
    setSubmitted(false)
    setScore(0)
    setFinished(false)
    setAttemptId(null)
    setTyped('')
    setGraded(null)
    setTypedError('')
  }, [quiz?.id])

  useEffect(() => {
    if (!quiz || attemptId || starting || questions.length === 0) return
    setStarting(true)
    quizzesAPI
      .startAttempt(quiz.id)
      .then((res) => setAttemptId(res.data.id))
      .catch(() => {})
      .finally(() => setStarting(false))
  }, [quiz, attemptId, starting, questions.length])

  // Enter checks (the form), Enter again advances, `r` overrides when
  // offered. Declared here, before any early return, so React sees the same
  // hooks on every render; the handlers arrive via keysRef (set below).
  const keysRef = useRef<{ next: () => void; override: () => void }>({
    next: () => {},
    override: () => {},
  })
  useEffect(() => {
    if (!typedMode) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && submitted) {
        e.preventDefault()
        keysRef.current.next()
      } else if (e.key === 'r' && submitted && graded && !graded.is_correct) {
        e.preventDefault()
        keysRef.current.override()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [typedMode, submitted, graded])

  if (!sourceParam || sourceIds.length === 0) {
    return <SourceRequired type="quiz" />
  }

  if (isLoading || starting) {
    return <p className="text-xl text-slate-500 text-center py-20">Loading quiz…</p>
  }

  if (!quiz || questions.length === 0) {
    return (
      <div className="text-center py-20 max-w-md mx-auto">
        <BookOpen className="size-16 text-slate-300 mx-auto mb-4" />
        <p className="text-xl text-slate-600 mb-6">No quiz for this source yet.</p>
        <Button asChild size="lg" className="bg-mode-quizzes hover:bg-mode-quizzes-hover text-white h-12 text-lg">
          <Link href="/dashboard/notebooks">Generate from Notebooks</Link>
        </Button>
      </div>
    )
  }

  if (finished) {
    const pct = Math.round((score / questions.length) * 100)
    return (
      <div className="rise max-w-2xl mx-auto text-center space-y-8 py-12">
        <CheckCircle2 className="size-20 text-mode-analytics mx-auto" />
        <h1 className="font-display text-3xl font-semibold text-slate-900">Quiz complete</h1>
        <p className="font-mono text-2xl text-slate-600 tabular-nums">
          {score} / {questions.length} correct ({pct}%)
        </p>
        <div className="flex gap-4 justify-center flex-wrap">
          <Button asChild size="lg" className="h-12 text-lg bg-mode-quizzes hover:bg-mode-quizzes-hover text-white">
            <Link href="/dashboard/notebooks">Back to sources</Link>
          </Button>
        </div>
      </div>
    )
  }

  const question = questions[qIndex]
  const options =
    question.question_type === 'true_false' && (!question.options?.length)
      ? ['True', 'False']
      : question.options ?? []

  const handleSubmit = async () => {
    if (!selected || !attemptId) return
    const correct = selected === question.correct_answer
    if (correct) setScore((s) => s + 1)

    try {
      await quizzesAPI.submitAnswer(attemptId, {
        question_id: question.id,
        answer: selected,
      })
    } catch {
      /* continue locally */
    }

    setSubmitted(true)
  }

  const handleCheckTyped = async () => {
    if (!typed.trim() || !attemptId || grading) return
    setGrading(true)
    setTypedError('')
    try {
      const res = await quizzesAPI.gradeTypedAnswer(attemptId, {
        question_id: question.id,
        answer: typed.trim(),
      })
      const g: Graded = res.data
      setGraded(g)
      if (g.is_correct) setScore((s) => s + 1)
      setSubmitted(true)
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status
      if (status === 503) {
        // No model on this server: fall back to choices for good this session.
        setTypedUnavailable(true)
        setTypedMode(false)
        setTypedError("Typed grading isn't available right now — pick an answer instead.")
      } else {
        setTypedError('Could not grade that answer. Check your connection and try again.')
      }
    } finally {
      setGrading(false)
    }
  }

  const handleOverride = async () => {
    if (!graded || !attemptId || graded.is_correct) return
    try {
      await quizzesAPI.overrideAnswer(attemptId, { answer_id: graded.id, is_correct: true })
      setGraded({ ...graded, is_correct: true })
      setScore((s) => s + 1)
    } catch {
      setTypedError('Could not record that. Try again.')
    }
  }

  const handleNext = async () => {
    if (qIndex >= questions.length - 1) {
      if (attemptId) {
        try {
          await quizzesAPI.completeQuiz(attemptId, {})
        } catch {
          /* ignore */
        }
      }
      setFinished(true)
      return
    }
    setQIndex((i) => i + 1)
    setSelected(null)
    setSubmitted(false)
    setTyped('')
    setGraded(null)
    setTypedError('')
  }

  // The keyboard effect above reaches these through a ref: they need
  // `question`, which only exists past the early returns, while hooks must
  // run in the same order on every render.
  keysRef.current = { next: () => void handleNext(), override: () => void handleOverride() }

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <Suspense fallback={null}>
        <SourceContextBanner />
      </Suspense>

      <div className="rise border-t-[3px] border-mode-quizzes pt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-quizzes">
            Quiz
          </p>
          <h1 className="font-display text-3xl font-semibold text-slate-900 mt-1">{quiz.title}</h1>
          <p className="font-mono text-sm text-slate-500 mt-1 tabular-nums">
            Question {qIndex + 1} of {questions.length}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {!typedUnavailable && (
            <Button
              type="button"
              variant={typedMode ? 'default' : 'outline'}
              size="lg"
              aria-pressed={typedMode}
              onClick={toggleTypedMode}
              className={
                typedMode
                  ? 'h-11 text-lg bg-mode-quizzes hover:bg-mode-quizzes-hover text-white'
                  : 'h-11 text-lg'
              }
            >
              <Keyboard className="size-5 mr-1.5" aria-hidden />
              Type answers
            </Button>
          )}
          <Button asChild variant="outline" size="lg" className="text-lg h-11">
            <Link href="/dashboard/notebooks">
              <ChevronLeft className="size-5 mr-1" />
              Sources
            </Link>
          </Button>
        </div>
      </div>

      <div className="rise h-1.5 rounded-full bg-slate-100 overflow-hidden" style={{ animationDelay: '60ms' }}>
        <div
          className="h-full bg-mode-quizzes transition-all duration-300"
          style={{ width: `${((qIndex + 1) / questions.length) * 100}%` }}
        />
      </div>

      <Card className="rise border-slate-200 shadow-sheet p-8 md:p-10" style={{ animationDelay: '120ms' }}>
        <div className="flex items-center gap-3 mb-6">
          <span className="font-mono text-sm font-semibold text-mode-quizzes tabular-nums">
            Q{String(qIndex + 1).padStart(2, '0')}
          </span>
          <span className="h-px flex-1 bg-slate-100" aria-hidden />
        </div>
        <p className="text-2xl md:text-3xl text-slate-900 leading-relaxed mb-8">
          {question.question_text}
        </p>

        {typedMode ? (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (!submitted) void handleCheckTyped()
            }}
          >
            {!submitted ? (
              <input
                autoFocus
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder="Type your answer"
                aria-label="Your answer"
                className="w-full rounded-xl border-2 border-slate-200 bg-white px-5 py-4 text-lg text-slate-900 focus:border-mode-quizzes focus:outline-none"
              />
            ) : graded ? (
              <TypedVerdict typed={typed} graded={graded} onOverride={handleOverride} />
            ) : null}
            {typedError && <p className="text-base text-red-700">{typedError}</p>}
          </form>
        ) : (
          <div className="space-y-3">
            {options.map((opt) => {
              let style = 'border-slate-200 bg-white hover:bg-slate-50'
              if (submitted) {
                if (opt === question.correct_answer) style = 'border-emerald-400 bg-emerald-50'
                else if (opt === selected) style = 'border-red-300 bg-red-50'
              } else if (selected === opt) {
                style = 'border-mode-quizzes bg-mode-quizzes/10'
              }
              return (
                <button
                  key={opt}
                  type="button"
                  disabled={submitted}
                  onClick={() => setSelected(opt)}
                  className={`w-full text-left rounded-xl border-2 px-5 py-4 text-lg text-slate-900 transition-colors ${style}`}
                >
                  {opt}
                </button>
              )
            })}
          </div>
        )}

        {submitted && !typedMode && question.explanation && (
          <p className="mt-6 text-lg text-slate-500 leading-relaxed">{question.explanation}</p>
        )}
      </Card>

      <div className="flex justify-center gap-4">
        {!submitted ? (
          <Button
            size="lg"
            disabled={typedMode ? !typed.trim() || grading : !selected}
            onClick={typedMode ? handleCheckTyped : handleSubmit}
            className="bg-mode-quizzes hover:bg-mode-quizzes-hover text-white h-12 px-10 text-lg"
          >
            {grading ? 'Checking…' : 'Check answer'}
          </Button>
        ) : (
          <Button
            size="lg"
            onClick={handleNext}
            className="bg-mode-quizzes hover:bg-mode-quizzes-hover text-white h-12 px-10 text-lg"
          >
            {qIndex >= questions.length - 1 ? 'Finish' : 'Next question'}
            <ArrowRight className="size-5 ml-2" />
          </Button>
        )}
      </div>
    </div>
  )
}

export default function QuizzesPage() {
  return (
    <Suspense fallback={<p className="text-xl text-slate-500 py-20 text-center">Loading…</p>}>
      <QuizzesStudy />
    </Suspense>
  )
}

/** What the grader said about a typed answer. Colour never stands alone:
 *  each state has its icon and its word. `near` and `wrong` offer the
 *  override — the student's judgement is the last word, and the label. */
function TypedVerdict({
  typed,
  graded,
  onOverride,
}: {
  typed: string
  graded: Graded
  onOverride: () => void
}) {
  const state = graded.is_correct
    ? { icon: CheckCircle2, word: 'Correct', tone: 'border-emerald-400 bg-emerald-50 text-emerald-900', iconTone: 'text-emerald-600' }
    : graded.verdict === 'near'
      ? { icon: CircleDashed, word: 'Close', tone: 'border-amber-400 bg-amber-50 text-amber-900', iconTone: 'text-amber-600' }
      : { icon: XCircle, word: 'Not quite', tone: 'border-red-300 bg-red-50 text-red-900', iconTone: 'text-red-600' }
  const Icon = state.icon
  return (
    <div className="space-y-4">
      <div className={`rounded-xl border-2 px-5 py-4 ${state.tone}`}>
        <p className="flex items-center gap-2 font-mono text-xs uppercase tracking-wide">
          <Icon className={`size-4 ${state.iconTone}`} aria-hidden />
          {state.word}
        </p>
        <p className="mt-1 text-lg">{typed}</p>
      </div>
      {!graded.is_correct && (
        <p className="text-lg text-slate-900">
          The answer is <span className="font-semibold">{graded.reference_answer}</span>.
        </p>
      )}
      {graded.explanation && (
        <p className="text-lg text-slate-500 leading-relaxed">{graded.explanation}</p>
      )}
      {!graded.is_correct && (
        <button
          type="button"
          onClick={onOverride}
          className="text-base text-slate-600 underline underline-offset-4 hover:text-slate-900"
        >
          I was right <span className="font-mono text-xs text-slate-400">(r)</span>
        </button>
      )}
    </div>
  )
}
