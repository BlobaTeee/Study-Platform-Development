'use client'

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import useSWR from 'swr'
import { mockTestsAPI, notebooksAPI } from '@/lib/api'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronLeft,
  Clock,
  Loader2,
  XCircle,
} from 'lucide-react'

type NotebookItem = {
  id: number
  title: string
}

type PaperQuestion = {
  id: number
  order: number
  question_text: string
  options: string[]
  user_answer: string | null
  correct_answer?: string
  explanation?: string
  is_correct?: boolean
}

type MockTest = {
  id: number
  deadline: string
  duration_minutes: number
  question_count: number
  notebook_title: string
  paper: PaperQuestion[]
  short_paper?: boolean
}

type SubmitResult = {
  id: number
  score: number
  completed_at: string
  question_count: number
  correct_count: number
  paper: PaperQuestion[]
}

/** 400s here name the offending field instead of using `detail` — try both
 *  before falling back to something generic. */
function apiErrorMessage(err: unknown, fallback: string): string {
  const ax = err as { response?: { data?: Record<string, unknown> } }
  const data = ax.response?.data
  if (!data) return fallback
  if (typeof data.detail === 'string') return data.detail
  for (const key of Object.keys(data)) {
    const val = data[key]
    if (Array.isArray(val) && typeof val[0] === 'string') return val[0]
    if (typeof val === 'string') return val
  }
  return fallback
}

function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds))
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}

function MockTestsInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const idParam = searchParams.get('id')

  const { data: nbData, isLoading: notebooksLoading } = useSWR(['/notebooks/'], () =>
    notebooksAPI.getNotebooks()
  )
  const notebooks: NotebookItem[] = nbData?.data?.results ?? nbData?.data ?? []

  const [notebookId, setNotebookId] = useState<number | ''>('')
  const [questionCount, setQuestionCount] = useState(20)
  const [durationMinutes, setDurationMinutes] = useState(30)
  const [starting, setStarting] = useState(false)
  const [setupError, setSetupError] = useState('')

  const [test, setTest] = useState<MockTest | null>(null)
  const [result, setResult] = useState<SubmitResult | null>(null)
  const [resuming, setResuming] = useState(!!idParam)

  const [qIndex, setQIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null)
  const [saveError, setSaveError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)

  useEffect(() => {
    if (!notebookId && notebooks.length > 0) setNotebookId(notebooks[0].id)
  }, [notebooks, notebookId])

  // Resuming after a refresh: the deadline the server hands back is the only
  // clock worth trusting, so re-fetching the test is how the countdown
  // survives a reload instead of quietly resetting to the full duration.
  useEffect(() => {
    if (!idParam || test) return
    let cancelled = false
    mockTestsAPI
      .get(Number(idParam))
      .then((res) => {
        if (cancelled) return
        const data = res.data as MockTest
        setTest(data)
        const initial: Record<number, string> = {}
        for (const q of data.paper) {
          if (q.user_answer) initial[q.id] = q.user_answer
        }
        setAnswers(initial)
      })
      .catch(() => {
        if (!cancelled) router.replace('/dashboard/tests')
      })
      .finally(() => {
        if (!cancelled) setResuming(false)
      })
    return () => {
      cancelled = true
    }
  }, [idParam, test, router])

  const paper = useMemo(
    () => [...(test?.paper ?? [])].sort((a, b) => a.order - b.order),
    [test]
  )

  const handleSubmit = useCallback(async () => {
    if (!test || submittingRef.current) return
    submittingRef.current = true
    setSubmitting(true)
    try {
      const res = await mockTestsAPI.submit(test.id)
      setResult(res.data)
    } catch {
      // The paper is already frozen server-side; there is nothing sensible
      // to retry into, so leave the student on the sitting view rather than
      // invent a failure state.
      submittingRef.current = false
    } finally {
      setSubmitting(false)
    }
  }, [test])

  // The countdown is display only: it is derived from the server's `deadline`
  // on every tick, never by counting `duration_minutes` down locally — a
  // slow page load must not hand out extra time.
  useEffect(() => {
    if (!test || result) return
    const deadlineMs = new Date(test.deadline).getTime()
    const tick = () => {
      const remaining = Math.max(0, Math.round((deadlineMs - Date.now()) / 1000))
      setSecondsRemaining(remaining)
      if (remaining <= 0) void handleSubmit()
    }
    tick()
    const interval = window.setInterval(tick, 1000)
    return () => window.clearInterval(interval)
  }, [test, result, handleSubmit])

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!notebookId) {
      setSetupError('Choose a notebook first.')
      return
    }
    setStarting(true)
    setSetupError('')
    try {
      const res = await mockTestsAPI.start({
        notebook: Number(notebookId),
        question_count: questionCount,
        duration_minutes: durationMinutes,
      })
      setAnswers({})
      setQIndex(0)
      setResult(null)
      setTest(res.data)
      router.replace(`/dashboard/tests?id=${res.data.id}`)
    } catch (err) {
      setSetupError(apiErrorMessage(err, 'Could not start the test. Is the backend running?'))
    } finally {
      setStarting(false)
    }
  }

  const selectAnswer = useCallback(
    async (question: PaperQuestion, option: string) => {
      if (!test || submittingRef.current) return
      setAnswers((prev) => ({ ...prev, [question.id]: option }))
      setSaveError('')
      try {
        await mockTestsAPI.answer(test.id, question.id, option)
      } catch (err: unknown) {
        const ax = err as { response?: { status?: number } }
        if (ax.response?.status === 409) {
          // Time is up regardless of what the countdown shows — hand the
          // paper in rather than arguing with the clock.
          void handleSubmit()
          return
        }
        setSaveError('Could not save that answer. Is the backend running?')
      }
    },
    [test, handleSubmit]
  )

  const goPrev = useCallback(() => setQIndex((i) => Math.max(0, i - 1)), [])
  const goNext = useCallback(
    () => setQIndex((i) => Math.min(paper.length - 1, i + 1)),
    [paper.length]
  )

  // Keyboard: arrows move between questions, number keys pick an option —
  // mirrors the number-key grading on the flashcards page.
  useEffect(() => {
    if (!test || result || paper.length === 0) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') {
        goNext()
      } else if (e.key === 'ArrowLeft') {
        goPrev()
      } else if (/^[1-9]$/.test(e.key)) {
        const q = paper[qIndex]
        const idx = Number(e.key) - 1
        if (q && q.options[idx] !== undefined) {
          e.preventDefault()
          void selectAnswer(q, q.options[idx])
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [test, result, paper, qIndex, goNext, goPrev, selectAnswer])

  const handleSubmitClick = () => {
    const unanswered = paper.length - Object.keys(answers).length
    const question = unanswered > 0 ? (unanswered === 1 ? 'question' : 'questions') : ''
    const confirmed =
      unanswered === 0 ||
      window.confirm(
        `${unanswered} ${question} still unanswered. Submit the test now?`
      )
    if (confirmed) void handleSubmit()
  }

  // ---- Review ----
  if (result) {
    const pct = result.question_count > 0 ? Math.round((result.correct_count / result.question_count) * 100) : 0
    const reviewPaper = [...result.paper].sort((a, b) => a.order - b.order)
    return (
      <div className="max-w-3xl mx-auto space-y-8">
        <div className="rise border-t-[3px] border-mode-quizzes pt-4 flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-quizzes">
              Mock test
            </p>
            <h1 className="font-display text-3xl font-semibold text-slate-900 mt-1">Reviewed</h1>
          </div>
          <Button asChild variant="outline" size="lg" className="text-lg h-11 shrink-0">
            <Link href="/dashboard/tests">
              <ChevronLeft className="size-5 mr-1" />
              New test
            </Link>
          </Button>
        </div>

        <Card className="rise border-slate-200 shadow-sheet p-8 md:p-10 text-center" style={{ animationDelay: '60ms' }}>
          <p className="font-mono text-4xl font-semibold text-slate-900 tabular-nums">
            {result.correct_count} / {result.question_count}
          </p>
          <p className="font-mono text-sm text-slate-500 mt-2 tabular-nums">{pct}% correct</p>
        </Card>

        <div className="space-y-5">
          {reviewPaper.map((q, i) => (
            <Card
              key={q.id}
              className="rise border-slate-200 shadow-sheet p-6 md:p-8"
              style={{ animationDelay: `${100 + i * 40}ms` }}
            >
              <div className="flex items-start gap-3 mb-4">
                <span className="font-mono text-sm font-semibold text-mode-quizzes tabular-nums shrink-0">
                  Q{String(q.order).padStart(2, '0')}
                </span>
                {q.is_correct ? (
                  <CheckCircle2 className="size-5 text-emerald-600 shrink-0 mt-0.5" aria-hidden />
                ) : (
                  <XCircle className="size-5 text-red-600 shrink-0 mt-0.5" aria-hidden />
                )}
                <p className="text-lg text-slate-900 leading-relaxed">{q.question_text}</p>
              </div>

              <div className="space-y-2 mb-4">
                {(q.options ?? []).map((opt) => {
                  let style = 'border-slate-200 bg-white text-slate-700'
                  if (opt === q.correct_answer) style = 'border-emerald-400 bg-emerald-50 text-emerald-900'
                  else if (opt === q.user_answer) style = 'border-red-300 bg-red-50 text-red-900'
                  return (
                    <div key={opt} className={`rounded-lg border-2 px-4 py-2.5 text-base ${style}`}>
                      {opt}
                      {opt === q.correct_answer && (
                        <span className="ml-2 font-mono text-xs uppercase tracking-wide text-emerald-700">
                          Correct answer
                        </span>
                      )}
                      {opt === q.user_answer && opt !== q.correct_answer && (
                        <span className="ml-2 font-mono text-xs uppercase tracking-wide text-red-700">
                          Your answer
                        </span>
                      )}
                    </div>
                  )
                })}
                {!q.user_answer && (
                  <p className="text-sm text-slate-500 italic">Left unanswered.</p>
                )}
              </div>

              {q.explanation && (
                <p className="text-base text-slate-500 leading-relaxed">{q.explanation}</p>
              )}
            </Card>
          ))}
        </div>
      </div>
    )
  }

  // ---- Resuming ----
  if (resuming) {
    return <p className="text-xl text-slate-500 text-center py-20">Loading test…</p>
  }

  // ---- Sitting ----
  if (test) {
    const question = paper[qIndex]
    const answeredCount = Object.keys(answers).length
    const low = secondsRemaining !== null && secondsRemaining <= 60

    return (
      <div className="max-w-3xl mx-auto space-y-8">
        <div className="rise border-t-[3px] border-mode-quizzes pt-4 flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-quizzes">
              Mock test
            </p>
            <h1 className="font-display text-3xl font-semibold text-slate-900 mt-1">
              {test.notebook_title}
            </h1>
            <p className="font-mono text-sm text-slate-500 mt-1 tabular-nums">
              Question {qIndex + 1} of {paper.length} · {answeredCount} answered
            </p>
          </div>
          <div
            className={`flex items-center gap-2 rounded-lg border-2 px-4 py-2 shrink-0 ${
              low ? 'border-red-300 bg-red-50 text-red-800' : 'border-mode-quizzes bg-mode-quizzes/10 text-mode-quizzes'
            }`}
            role="timer"
            aria-live="polite"
          >
            <Clock className="size-5" aria-hidden />
            <div className="leading-tight">
              <p className="font-mono text-lg font-semibold tabular-nums">
                {secondsRemaining !== null ? formatClock(secondsRemaining) : '—:—'}
              </p>
              <p className="text-[11px] uppercase tracking-wide">Time remaining</p>
            </div>
          </div>
        </div>

        {test.short_paper && (
          <p className="rise text-sm text-slate-500">
            This notebook only had {test.question_count} question{test.question_count === 1 ? '' : 's'} available, so the
            paper is shorter than requested.
          </p>
        )}

        <div className="rise h-1.5 rounded-full bg-slate-100 overflow-hidden" style={{ animationDelay: '60ms' }}>
          <div
            className="h-full bg-mode-quizzes transition-all duration-300 motion-reduce:transition-none"
            style={{ width: `${((qIndex + 1) / Math.max(1, paper.length)) * 100}%` }}
          />
        </div>

        {/* Question palette: jump to any question, answered ones marked so
            no state is carried by colour alone. */}
        <div className="rise flex flex-wrap gap-2" style={{ animationDelay: '90ms' }}>
          {paper.map((q, i) => {
            const isAnswered = answers[q.id] !== undefined
            const isCurrent = i === qIndex
            return (
              <button
                key={q.id}
                type="button"
                onClick={() => setQIndex(i)}
                aria-current={isCurrent}
                aria-label={`Question ${i + 1}${isAnswered ? ', answered' : ', not answered'}`}
                className={`size-9 rounded-md border-2 font-mono text-sm tabular-nums transition-colors outline-none focus-visible:ring-4 focus-visible:ring-mode-quizzes/30 ${
                  isCurrent
                    ? 'border-mode-quizzes bg-mode-quizzes text-white'
                    : isAnswered
                      ? 'border-mode-quizzes/40 bg-mode-quizzes/10 text-mode-quizzes'
                      : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
                }`}
              >
                {i + 1}
              </button>
            )
          })}
        </div>

        {question && (
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

            <div className="space-y-3" role="radiogroup" aria-label="Answer options">
              {(question.options ?? []).map((opt) => {
                const isSelected = answers[question.id] === opt
                return (
                  <button
                    key={opt}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    onClick={() => selectAnswer(question, opt)}
                    className={`w-full text-left rounded-xl border-2 px-5 py-4 text-lg text-slate-900 transition-colors outline-none focus-visible:ring-4 focus-visible:ring-mode-quizzes/30 motion-reduce:transition-none ${
                      isSelected ? 'border-mode-quizzes bg-mode-quizzes/10' : 'border-slate-200 bg-white hover:bg-slate-50'
                    }`}
                  >
                    {opt}
                  </button>
                )
              })}
            </div>
          </Card>
        )}

        {saveError && (
          <p role="alert" className="rise text-center text-sm text-red-700">
            {saveError}
          </p>
        )}

        <div className="flex justify-center gap-4 flex-wrap">
          <Button
            variant="outline"
            size="lg"
            onClick={goPrev}
            disabled={qIndex === 0}
            className="h-12 px-6 text-lg"
          >
            <ArrowLeft className="size-5 mr-2" />
            Previous
          </Button>
          {qIndex < paper.length - 1 ? (
            <Button
              size="lg"
              onClick={goNext}
              className="bg-mode-quizzes hover:bg-mode-quizzes-hover text-white h-12 px-6 text-lg"
            >
              Next question
              <ArrowRight className="size-5 ml-2" />
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="lg"
            onClick={handleSubmitClick}
            disabled={submitting}
            className="h-12 px-6 text-lg border-mode-quizzes text-mode-quizzes hover:bg-mode-quizzes/10"
          >
            {submitting ? <Loader2 className="size-4 animate-spin mr-2" /> : null}
            Submit test
          </Button>
        </div>
      </div>
    )
  }

  // ---- Setup ----
  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div className="rise border-t-[3px] border-mode-quizzes pt-4">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-quizzes">
          Mock test
        </p>
        <h1 className="font-display text-3xl font-semibold text-slate-900 mt-1">Sit a timed test</h1>
        <p className="text-base text-slate-500 mt-2 leading-relaxed">
          Pick a notebook, a paper length and a duration. Once the test starts, the paper is fixed and the
          clock runs until you submit or time runs out.
        </p>
      </div>

      {notebooksLoading ? (
        <p className="text-lg text-slate-500 text-center py-12">Loading notebooks…</p>
      ) : notebooks.length === 0 ? (
        <div className="text-center py-16 max-w-md mx-auto">
          <BookOpen className="size-16 text-slate-300 mx-auto mb-4" />
          <p className="text-xl text-slate-600 mb-6">No notebooks yet.</p>
          <Button asChild size="lg" className="bg-mode-quizzes hover:bg-mode-quizzes-hover text-white h-12 text-lg">
            <Link href="/dashboard/notebooks">Go to Notebooks</Link>
          </Button>
        </div>
      ) : (
        <Card className="rise border-slate-200 shadow-sheet p-6 md:p-8" style={{ animationDelay: '60ms' }}>
          <form onSubmit={handleStart} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="test-notebook">Notebook</Label>
              <select
                id="test-notebook"
                value={notebookId}
                onChange={(e) => setNotebookId(Number(e.target.value))}
                className="h-11 w-full rounded-lg border border-slate-300 bg-white px-3.5 text-base text-slate-900 shadow-sm outline-none focus-visible:border-mode-quizzes focus-visible:ring-mode-quizzes/25 focus-visible:ring-[4px]"
              >
                {notebooks.map((nb) => (
                  <option key={nb.id} value={nb.id}>
                    {nb.title}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid sm:grid-cols-2 gap-5">
              <div className="space-y-2">
                <Label htmlFor="test-count">Questions</Label>
                <Input
                  id="test-count"
                  type="number"
                  min={5}
                  max={50}
                  value={questionCount}
                  onChange={(e) => setQuestionCount(Number(e.target.value))}
                />
                <p className="text-sm text-slate-500">Between 5 and 50.</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="test-duration">Duration (minutes)</Label>
                <Input
                  id="test-duration"
                  type="number"
                  min={5}
                  max={180}
                  value={durationMinutes}
                  onChange={(e) => setDurationMinutes(Number(e.target.value))}
                />
                <p className="text-sm text-slate-500">Between 5 and 180.</p>
              </div>
            </div>

            {setupError && (
              <div className="flex gap-3 rounded-lg bg-red-50 p-4 border border-red-200">
                <AlertCircle className="size-5 text-mode-danger shrink-0" />
                <p className="text-base text-red-700">{setupError}</p>
              </div>
            )}

            <Button
              type="submit"
              size="lg"
              disabled={starting || !notebookId}
              className="w-full bg-mode-quizzes hover:bg-mode-quizzes-hover text-white h-12 text-lg"
            >
              {starting ? (
                <>
                  <Loader2 className="size-4 animate-spin mr-2" />
                  Starting…
                </>
              ) : (
                'Start test'
              )}
            </Button>
          </form>
        </Card>
      )}
    </div>
  )
}

export default function MockTestsPage() {
  return (
    <Suspense fallback={<p className="text-xl text-slate-500 py-20 text-center">Loading…</p>}>
      <MockTestsInner />
    </Suspense>
  )
}
