'use client'

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import useSWR from 'swr'
import { mockTestsAPI, notebooksAPI, plannedTestsAPI } from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'
import { useLocale, useTranslations } from 'next-intl'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Bell,
  BellRing,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  Clock,
  Loader2,
  Trash2,
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
  source?: { id: number; title: string; notebook: number } | null
  source_excerpt?: string
}

type MockTest = {
  id: number
  deadline: string
  duration_minutes: number
  question_count: number
  notebook_title: string
  paper: PaperQuestion[]
  short_paper?: boolean
  // Present on GET but not on the start response's shape we rely on; used
  // only to detect "this test is already finished" on resume.
  completed_at?: string | null
  score?: number | null
}

type SubmitResult = {
  id: number
  notebook: number
  score: number
  completed_at: string
  question_count: number
  correct_count: number
  // Size of the notebook's mistake bank after this sitting was marked.
  mistake_count: number
  paper: PaperQuestion[]
}

type PlannedTest = {
  id: number
  notebook: number
  notebook_title: string
  scheduled_for: string
  question_count: number
  duration_minutes: number
  reminder_lead_hours: number
  reminder_sent_at: string | null
  mock_test: number | null
  sat_at: string | null
  created_at: string
}

// Keys under `tests` for the three reminder leads the API accepts.
const REMINDER_LEAD_KEYS: Record<number, 'lead1h' | 'lead1d' | 'lead3d'> = {
  1: 'lead1h',
  24: 'lead1d',
  72: 'lead3d',
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

function formatScheduledFor(iso: string, locale: string): string {
  return new Date(iso).toLocaleString(locale, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

// For the disabled Start button. The card already shows the full date a line
// above, so the button only repeats the time — unless the plan is on another
// day, when a bare time would read as today.
function formatOpensAt(iso: string, locale: string): string {
  const at = new Date(iso)
  const sameDay = at.toDateString() === new Date().toDateString()
  return at.toLocaleString(locale, {
    ...(sameDay ? {} : { month: 'short', day: 'numeric' }),
    hour: 'numeric',
    minute: '2-digit',
  })
}

function MockTestsInner() {
  const t = useTranslations('tests')
  const common = useTranslations('common')
  const locale = useLocale()
  const router = useRouter()
  const searchParams = useSearchParams()
  const idParam = searchParams.get('id')

  const { data: nbData, isLoading: notebooksLoading } = useSWR(['/notebooks/'], () =>
    notebooksAPI.getNotebooks()
  )
  const notebooks: NotebookItem[] = nbData?.data?.results ?? nbData?.data ?? []

  const [notebookId, setNotebookId] = useState<number | ''>('')
  const [questionCount, setQuestionCount] = useState<number | ''>(20)
  const [durationMinutes, setDurationMinutes] = useState<number | ''>(30)
  const [starting, setStarting] = useState(false)
  const [confirm, confirmDialog] = useConfirm()
  const [setupError, setSetupError] = useState('')
  // Keyed by notebook so a count fetched for the previous pick never shows
  // under the new one; `mistakeCount` below is null until this one's arrives.
  const [bank, setBank] = useState<{ notebook: number; count: number } | null>(null)
  const mistakeCount = bank && bank.notebook === notebookId ? bank.count : null
  const [retaking, setRetaking] = useState(false)

  const {
    data: plansData,
    isLoading: plansLoading,
    mutate: mutatePlans,
  } = useSWR(['/quizzes/planned-tests/'], () => plannedTestsAPI.list())
  const plans: PlannedTest[] = plansData?.data?.results ?? plansData?.data ?? []

  const [planNotebookId, setPlanNotebookId] = useState<number | ''>('')
  const [planScheduledFor, setPlanScheduledFor] = useState('')
  const [planQuestionCount, setPlanQuestionCount] = useState<number | ''>(20)
  const [planDurationMinutes, setPlanDurationMinutes] = useState<number | ''>(30)
  const [planReminderLead, setPlanReminderLead] = useState<number>(24)
  const [planCreating, setPlanCreating] = useState(false)
  const [planError, setPlanError] = useState('')
  const [startingPlanId, setStartingPlanId] = useState<number | null>(null)
  const [cancelingPlanId, setCancelingPlanId] = useState<number | null>(null)
  // A plan can't be started before its booked time. This clock exists so the
  // button enables itself when that time arrives instead of waiting for a
  // refresh; the server re-checks regardless, so it is display only.
  const [nowMs, setNowMs] = useState(() => Date.now())

  const [test, setTest] = useState<MockTest | null>(null)
  const [result, setResult] = useState<SubmitResult | null>(null)
  const [resuming, setResuming] = useState(!!idParam)

  const [qIndex, setQIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null)
  const [saveError, setSaveError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)
  // Set by handleNewTest, checked (and cleared) by the resume effect below.
  // router.replace('/dashboard/tests') drops `?id=` asynchronously, but the
  // setState calls in the same handler are urgent and can commit a render
  // first — one where `test`/`result` are already null while `idParam`
  // still holds the id of the test just left behind. Without this flag that
  // render's resume effect would treat it as "test/result missing, id
  // present" and re-fetch (and, for an already-submitted test, re-submit),
  // silently undoing the reset the student just asked for.
  const justResetRef = useRef(false)

  useEffect(() => {
    if (!notebookId && notebooks.length > 0) setNotebookId(notebooks[0].id)
  }, [notebooks, notebookId])

  useEffect(() => {
    if (!planNotebookId && notebooks.length > 0) setPlanNotebookId(notebooks[0].id)
  }, [notebooks, planNotebookId])

  // The bank is per notebook, so it follows the picker. `result` is in the
  // deps so the count refreshes when a sitting is marked and again when
  // the student comes back to setup.
  useEffect(() => {
    if (!notebookId) return
    let cancelled = false
    const notebook = Number(notebookId)
    mockTestsAPI
      .mistakes(notebook)
      .then((res) => {
        if (!cancelled) setBank({ notebook, count: res.data.count })
      })
      .catch(() => {
        // Leave it unknown: the setup form just omits the line.
      })
    return () => {
      cancelled = true
    }
  }, [notebookId, result])

  // Resuming after a refresh: the deadline the server hands back is the only
  // clock worth trusting, so re-fetching the test is how the countdown
  // survives a reload instead of quietly resetting to the full duration.
  //
  // A resumed test can already be finished (submitted before the refresh, or
  // auto-submitted the instant the deadline passed). The GET withholds
  // marking, so an already-completed test cannot go through the sitting
  // view at all — that would just re-trigger the deadline-passed auto-submit
  // against a paper with no legitimate "unfinished" state to resolve into.
  // Instead, fetch the review via the idempotent submit endpoint, which
  // returns the existing marked-up paper without re-grading.
  useEffect(() => {
    if (justResetRef.current) {
      // See the comment on justResetRef: this render is the transient one
      // where the URL hasn't caught up with the just-reset state yet.
      // Swallow it once and let the next render (with `idParam` actually
      // cleared) take the normal early-return path below.
      justResetRef.current = false
      return
    }
    if (!idParam || test || result) return
    let cancelled = false
    mockTestsAPI
      .get(Number(idParam))
      .then((res) => {
        if (cancelled) return
        const data = res.data as MockTest
        if (data.completed_at) {
          return mockTestsAPI.submit(data.id).then((subRes) => {
            if (!cancelled) setResult(subRes.data)
          })
        }
        setTest(data)
        const initial: Record<number, string> = {}
        for (const q of data.paper) {
          if (q.user_answer) initial[q.id] = q.user_answer
        }
        setAnswers(initial)
        return undefined
      })
      .catch(() => {
        // Covers a 404'd id and a failure of the review fetch above alike:
        // there is nothing sensible left to resume, so fall back to Setup
        // rather than leaving the student on a permanent loading state.
        if (!cancelled) router.replace('/dashboard/tests')
      })
      .finally(() => {
        if (!cancelled) setResuming(false)
      })
    return () => {
      cancelled = true
    }
  }, [idParam, test, result, router])

  const paper = useMemo(
    () => [...(test?.paper ?? [])].sort((a, b) => a.order - b.order),
    [test]
  )

  const handleSubmit = useCallback(async () => {
    if (!test || submittingRef.current) return
    submittingRef.current = true
    setSubmitting(true)
    setSubmitError('')
    try {
      const res = await mockTestsAPI.submit(test.id)
      setResult(res.data)
    } catch (err) {
      // Submit is idempotent server-side, so retrying is fine in principle —
      // but a *persistent* failure (backend down, network gone) must surface
      // to the student and stop firing on every countdown tick rather than
      // retry silently forever. `submitError` being non-empty is what tells
      // the tick effect below to stand down; the "try again" affordance in
      // the UI is the only thing allowed to attempt it again after that.
      submittingRef.current = false
      setSubmitError(apiErrorMessage(err, t('submitFailed')))
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
      // Once a submit attempt has failed, stop auto-retrying on every tick —
      // that's the infinite-loop trap. The student sees `submitError` and a
      // manual retry button instead.
      if (remaining <= 0 && !submitError) void handleSubmit()
    }
    tick()
    const interval = window.setInterval(tick, 1000)
    return () => window.clearInterval(interval)
  }, [test, result, handleSubmit, submitError])

  // Only runs while some plan is still waiting to open, and at 30s: the
  // countdown above needs seconds, this only needs to flip a button within a
  // half minute of its time, and most visits have nothing pending at all.
  useEffect(() => {
    const pending = plans.some(
      (p) => !p.sat_at && new Date(p.scheduled_for).getTime() > nowMs
    )
    if (!pending) return
    const interval = window.setInterval(() => setNowMs(Date.now()), 30_000)
    return () => window.clearInterval(interval)
  }, [plans, nowMs])

  // New test: reset every bit of the previous attempt's state, not just the
  // URL. `/dashboard/tests` is the same route segment as the current URL
  // (only the `?id=` query differs), so Next does not remount this
  // component on that navigation — without this, `result`/`test`/`answers`
  // would keep the review screen on the page forever.
  const handleNewTest = useCallback(() => {
    justResetRef.current = true
    submittingRef.current = false
    setResult(null)
    setTest(null)
    setAnswers({})
    setQIndex(0)
    setSecondsRemaining(null)
    setSaveError('')
    setSubmitError('')
    setResuming(false)
    router.replace('/dashboard/tests')
  }, [router])

  // Shared by the setup form and a plan's "Start now" — both just need to
  // hand the server a notebook and a shape and land on the same sitting view.
  // `planned_test` is only ever set by handleStartFromPlan, so a fresh setup
  // never mistakenly links itself to somebody's leftover plan.
  const beginTest = useCallback(
    async (params: {
      notebook: number
      question_count?: number
      duration_minutes: number
      planned_test?: number
      mistakes_only?: boolean
    }) => {
      const res = await mockTestsAPI.start(params)
      setAnswers({})
      setQIndex(0)
      setResult(null)
      setTest(res.data)
      router.replace(`/dashboard/tests?id=${res.data.id}`)
    },
    [router]
  )

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!notebookId) {
      setSetupError(t('chooseNotebook'))
      return
    }
    if (questionCount === '' || durationMinutes === '') {
      setSetupError(t('enterCountAndDuration'))
      return
    }
    setStarting(true)
    setSetupError('')
    try {
      await beginTest({
        notebook: Number(notebookId),
        question_count: questionCount,
        duration_minutes: durationMinutes,
      })
    } catch (err) {
      setSetupError(apiErrorMessage(err, t('startFailed')))
    } finally {
      setStarting(false)
    }
  }

  // Sits the whole bank for a notebook: from the setup form (its duration
  // field) or straight from a review (the default duration).
  const handleRetakeMistakes = async (notebook: number, duration: number) => {
    setRetaking(true)
    setSetupError('')
    try {
      await beginTest({ notebook, duration_minutes: duration, mistakes_only: true })
    } catch (err) {
      setSetupError(apiErrorMessage(err, t('startFailed')))
    } finally {
      setRetaking(false)
    }
  }

  const handleStartFromPlan = async (plan: PlannedTest) => {
    setStartingPlanId(plan.id)
    setPlanError('')
    try {
      await beginTest({
        notebook: plan.notebook,
        question_count: plan.question_count,
        duration_minutes: plan.duration_minutes,
        planned_test: plan.id,
      })
      void mutatePlans()
    } catch (err) {
      setPlanError(apiErrorMessage(err, t('startFailed')))
    } finally {
      setStartingPlanId(null)
    }
  }

  const handleCreatePlan = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!planNotebookId) {
      setPlanError(t('chooseNotebook'))
      return
    }
    if (!planScheduledFor) {
      setPlanError(t('pickDateTime'))
      return
    }
    if (planQuestionCount === '' || planDurationMinutes === '') {
      setPlanError(t('enterCountAndDuration'))
      return
    }
    setPlanCreating(true)
    setPlanError('')
    try {
      // `datetime-local` carries no timezone of its own. `new Date(...)`
      // parses it in the browser's local zone, and `.toISOString()` is what
      // turns that into the UTC instant the backend stores and compares
      // `scheduled_for` against — posting the raw string would leave the
      // server guessing the zone.
      const scheduledForIso = new Date(planScheduledFor).toISOString()
      await plannedTestsAPI.create({
        notebook: Number(planNotebookId),
        scheduled_for: scheduledForIso,
        question_count: planQuestionCount,
        duration_minutes: planDurationMinutes,
        reminder_lead_hours: planReminderLead,
      })
      setPlanScheduledFor('')
      setPlanQuestionCount(20)
      setPlanDurationMinutes(30)
      setPlanReminderLead(24)
      void mutatePlans()
    } catch (err) {
      // A past scheduled_for comes back as a field error naming
      // scheduled_for ("Pick a time in the future.") — surface it as-is
      // rather than a generic failure.
      setPlanError(apiErrorMessage(err, t('planFailed')))
    } finally {
      setPlanCreating(false)
    }
  }

  const handleCancelPlan = async (id: number) => {
    setCancelingPlanId(id)
    setPlanError('')
    try {
      await plannedTestsAPI.remove(id)
      void mutatePlans()
    } catch {
      setPlanError(t('cancelFailed'))
    } finally {
      setCancelingPlanId(null)
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
        setSaveError(t('saveFailed'))
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

  const handleSubmitClick = async () => {
    const unanswered = paper.length - Object.keys(answers).length
    if (unanswered > 0) {
      const ok = await confirm({
        title: t('unansweredTitle', { questions: common('questions', { count: unanswered }) }),
        body: t('unansweredBody'),
        confirmLabel: t('submitAnyway'),
        cancelLabel: common('cancel'),
      })
      if (!ok) return
    }
    void handleSubmit()
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
              {t('eyebrow')}
            </p>
            <h1 className="font-display text-3xl font-semibold text-slate-900 mt-1">{t('reviewed')}</h1>
          </div>
          <Button variant="outline" size="lg" className="text-lg h-11 shrink-0" onClick={handleNewTest}>
            <ChevronLeft className="size-5 mr-1" />
            {t('newTest')}
          </Button>
        </div>

        <Card className="rise border-slate-200 shadow-sheet p-8 md:p-10 text-center" style={{ animationDelay: '60ms' }}>
          <p className="font-mono text-4xl font-semibold text-slate-900 tabular-nums">
            {result.correct_count} / {result.question_count}
          </p>
          <p className="font-mono text-sm text-slate-500 mt-2 tabular-nums">{t('pctCorrect', { pct })}</p>
        </Card>

        {/* The bank, not just this paper's misses: a question cleared today
            drops out, one missed last week and again today is still one. */}
        <Card className="rise border-slate-200 shadow-sheet p-5 md:p-6 items-center text-center gap-3" style={{ animationDelay: '80ms' }}>
          <p className="text-base text-slate-700">
            {result.mistake_count > 0
              ? t('mistakesAfterTest', { count: result.mistake_count })
              : t('bankClear')}
          </p>
          {result.mistake_count > 0 && (
            <Button
              variant="outline"
              size="lg"
              disabled={retaking}
              className="h-11 text-base border-mode-quizzes text-mode-quizzes hover:bg-mode-quizzes/10"
              onClick={() => void handleRetakeMistakes(result.notebook, 30)}
            >
              {retaking ? <Loader2 className="size-4 animate-spin mr-2" /> : null}
              {t('retakeMistakes')}
            </Button>
          )}
          {setupError && <p className="text-sm text-red-700">{setupError}</p>}
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
                          {t('correctAnswer')}
                        </span>
                      )}
                      {opt === q.user_answer && opt !== q.correct_answer && (
                        <span className="ml-2 font-mono text-xs uppercase tracking-wide text-red-700">
                          {t('yourAnswer')}
                        </span>
                      )}
                    </div>
                  )
                })}
                {!q.user_answer && (
                  <p className="text-sm text-slate-500 italic">{t('leftUnanswered')}</p>
                )}
              </div>

              {q.explanation && (
                <p className="text-base text-slate-500 leading-relaxed">{q.explanation}</p>
              )}
              {(q.source || q.source_excerpt) && (
                <Provenance source={q.source ?? null} excerpt={q.source_excerpt ?? ''} />
              )}
            </Card>
          ))}
        </div>
      </div>
    )
  }

  // ---- Resuming ----
  if (resuming) {
    return <p className="text-xl text-slate-500 text-center py-20">{t('loadingTest')}</p>
  }

  // ---- Sitting ----
  if (test) {
    const question = paper[qIndex]
    const answeredCount = Object.keys(answers).length
    const low = secondsRemaining !== null && secondsRemaining <= 60

    return (
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Only this branch confirms anything (submitting with blanks), so the
            dialog belongs here rather than in every return. */}
        {confirmDialog}
        <div className="rise border-t-[3px] border-mode-quizzes pt-4 flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-quizzes">
              {t('eyebrow')}
            </p>
            <h1 className="font-display text-3xl font-semibold text-slate-900 mt-1">
              {test.notebook_title}
            </h1>
            <p className="font-mono text-sm text-slate-500 mt-1 tabular-nums">
              {t('questionOf', { n: qIndex + 1, total: paper.length, answered: answeredCount })}
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
              <p className="text-[11px] uppercase tracking-wide">{t('timeRemaining')}</p>
            </div>
          </div>
        </div>

        {test.short_paper && (
          <p className="rise text-sm text-slate-500">
            {t('shortPaper', { questions: common('questions', { count: test.question_count }) })}
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
                aria-label={`${t('questionLabel', { n: i + 1 })}, ${isAnswered ? t('answered') : t('notAnswered')}`}
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

        {submitError && (
          <div role="alert" className="rise flex flex-col items-center gap-3 text-center">
            <p className="text-sm text-red-700">{submitError}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void handleSubmit()}
              className="border-mode-quizzes text-mode-quizzes hover:bg-mode-quizzes/10"
            >
              {t('trySubmitAgain')}
            </Button>
          </div>
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
            {t('previous')}
          </Button>
          {qIndex < paper.length - 1 ? (
            <Button
              size="lg"
              onClick={goNext}
              className="bg-mode-quizzes hover:bg-mode-quizzes-hover text-white h-12 px-6 text-lg"
            >
              {t('nextQuestion')}
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
            {t('submitTest')}
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
          {t('eyebrow')}
        </p>
        <h1 className="font-display text-3xl font-semibold text-slate-900 mt-1">{t('sitTitle')}</h1>
        <p className="text-base text-slate-500 mt-2 leading-relaxed">
          {t('sitLead')}
        </p>
      </div>

      {notebooksLoading ? (
        <p className="text-lg text-slate-500 text-center py-12">{t('loadingNotebooks')}</p>
      ) : notebooks.length === 0 ? (
        <div className="text-center py-16 max-w-md mx-auto">
          <BookOpen className="size-16 text-slate-300 mx-auto mb-4" />
          <p className="text-xl text-slate-600 mb-6">{t('noNotebooks')}</p>
          <Button asChild size="lg" className="bg-mode-quizzes hover:bg-mode-quizzes-hover text-white h-12 text-lg">
            <Link href="/dashboard/notebooks">{t('goToNotebooks')}</Link>
          </Button>
        </div>
      ) : (
        <Card className="rise border-slate-200 shadow-sheet p-6 md:p-8" style={{ animationDelay: '60ms' }}>
          <form onSubmit={handleStart} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="test-notebook">{t('notebook')}</Label>
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
                <Label htmlFor="test-count">{t('questions')}</Label>
                <Input
                  id="test-count"
                  type="number"
                  min={5}
                  max={50}
                  value={questionCount}
                  onChange={(e) => {
                    const v = e.target.value
                    setQuestionCount(v === '' ? '' : Number(v))
                  }}
                />
                <p className="text-sm text-slate-500">Between 5 and 50.</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="test-duration">{t('duration')}</Label>
                <Input
                  id="test-duration"
                  type="number"
                  min={5}
                  max={180}
                  value={durationMinutes}
                  onChange={(e) => {
                    const v = e.target.value
                    setDurationMinutes(v === '' ? '' : Number(v))
                  }}
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
                  {t('buildingPaper')}
                </>
              ) : (
                t('startTest')
              )}
            </Button>
            {/* Starting is instant when the notebook already holds enough
                questions, and up to a minute when it has to generate the
                rest. Without saying so, the second case reads as a hang. */}
            {starting && (
              <p className="text-sm text-slate-500 text-center">
                {t('generatingNote')}
              </p>
            )}

            {mistakeCount !== null && (
              <div className="border-t border-slate-200 pt-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-base text-slate-700">{t('mistakeBank', { count: mistakeCount })}</p>
                  <p className="text-sm text-slate-500">{t('mistakeBankHint')}</p>
                </div>
                {mistakeCount > 0 && (
                  <Button
                    type="button"
                    variant="outline"
                    disabled={retaking || starting || durationMinutes === ''}
                    className="h-10 border-mode-quizzes text-mode-quizzes hover:bg-mode-quizzes/10"
                    onClick={() => void handleRetakeMistakes(Number(notebookId), Number(durationMinutes))}
                  >
                    {retaking ? <Loader2 className="size-4 animate-spin mr-2" /> : null}
                    {t('retakeMistakes')}
                  </Button>
                )}
              </div>
            )}
          </form>
        </Card>
      )}

      <div className="rise space-y-6" style={{ animationDelay: '120ms' }}>
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-quizzes">
            {t('plannedTests')}
          </p>
          <h2 className="font-display text-2xl font-semibold text-slate-900 mt-1">{t('planAhead')}</h2>
          <p className="text-base text-slate-500 mt-2 leading-relaxed">
            {t('planLead')}
          </p>
        </div>

        {notebooks.length > 0 && (
          <Card className="border-slate-200 shadow-sheet p-6 md:p-8">
            <form onSubmit={handleCreatePlan} className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="plan-notebook">{t('notebook')}</Label>
                <select
                  id="plan-notebook"
                  value={planNotebookId}
                  onChange={(e) => setPlanNotebookId(Number(e.target.value))}
                  className="h-11 w-full rounded-lg border border-slate-300 bg-white px-3.5 text-base text-slate-900 shadow-sm outline-none focus-visible:border-mode-quizzes focus-visible:ring-mode-quizzes/25 focus-visible:ring-[4px]"
                >
                  {notebooks.map((nb) => (
                    <option key={nb.id} value={nb.id}>
                      {nb.title}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="plan-when">{t('dateTime')}</Label>
                <Input
                  id="plan-when"
                  type="datetime-local"
                  value={planScheduledFor}
                  onChange={(e) => setPlanScheduledFor(e.target.value)}
                  className="h-11"
                />
              </div>

              <div className="grid sm:grid-cols-3 gap-5">
                <div className="space-y-2">
                  <Label htmlFor="plan-count">{t('questions')}</Label>
                  <Input
                    id="plan-count"
                    type="number"
                    min={5}
                    max={50}
                    value={planQuestionCount}
                    onChange={(e) => {
                      const v = e.target.value
                      setPlanQuestionCount(v === '' ? '' : Number(v))
                    }}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="plan-duration">{t('duration')}</Label>
                  <Input
                    id="plan-duration"
                    type="number"
                    min={5}
                    max={180}
                    value={planDurationMinutes}
                    onChange={(e) => {
                      const v = e.target.value
                      setPlanDurationMinutes(v === '' ? '' : Number(v))
                    }}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="plan-reminder">{t('reminder')}</Label>
                  <select
                    id="plan-reminder"
                    value={planReminderLead}
                    onChange={(e) => setPlanReminderLead(Number(e.target.value))}
                    className="h-11 w-full rounded-lg border border-slate-300 bg-white px-3.5 text-base text-slate-900 shadow-sm outline-none focus-visible:border-mode-quizzes focus-visible:ring-mode-quizzes/25 focus-visible:ring-[4px]"
                  >
                    <option value={1}>{t('lead1h')}</option>
                    <option value={24}>{t('lead1d')}</option>
                    <option value={72}>{t('lead3d')}</option>
                  </select>
                </div>
              </div>

              {planError && (
                <div className="flex gap-3 rounded-lg bg-red-50 p-4 border border-red-200">
                  <AlertCircle className="size-5 text-mode-danger shrink-0" />
                  <p className="text-base text-red-700">{planError}</p>
                </div>
              )}

              <Button
                type="submit"
                size="lg"
                disabled={planCreating || !planNotebookId}
                className="w-full bg-mode-quizzes hover:bg-mode-quizzes-hover text-white h-12 text-lg"
              >
                {planCreating ? (
                  <>
                    <Loader2 className="size-4 animate-spin mr-2" />
                    {t('planning')}
                  </>
                ) : (
                  t('planTest')
                )}
              </Button>
            </form>
          </Card>
        )}

        {plansLoading ? (
          <p className="text-lg text-slate-500 text-center py-8">Loading planned tests…</p>
        ) : plans.length === 0 ? (
          <p className="text-base text-slate-500 text-center py-8">{t('noPlans')}</p>
        ) : (
          <div className="space-y-3">
            {plans.map((plan) => (
              <Card key={plan.id} className="border-slate-200 shadow-sheet p-5 md:p-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-lg font-medium text-slate-900 truncate">{plan.notebook_title}</p>
                    <p className="flex items-center gap-1.5 text-sm text-slate-500 mt-1">
                      <CalendarClock className="size-4 shrink-0" aria-hidden />
                      {formatScheduledFor(plan.scheduled_for, locale)}
                    </p>
                    <p className="font-mono text-sm text-slate-500 mt-1 tabular-nums">
                      {t('planShape', { questions: common('questions', { count: plan.question_count }), minutes: common('minutes', { count: plan.duration_minutes }) })}
                    </p>
                    {plan.sat_at ? (
                      // Sat takes priority over the reminder line: once a plan
                      // has been fulfilled, whether its reminder ever fired is
                      // no longer the relevant fact about it. Icon + label,
                      // not colour alone, same as the reminder states below.
                      <p className="flex items-center gap-1.5 text-sm text-mode-quizzes mt-2">
                        <CheckCircle2 className="size-4 shrink-0" aria-hidden />
                        {t('sat')}
                      </p>
                    ) : plan.reminder_sent_at ? (
                      <p className="flex items-center gap-1.5 text-sm text-mode-quizzes mt-2">
                        <BellRing className="size-4 shrink-0" aria-hidden />
                        {t('reminderSent')}
                      </p>
                    ) : (
                      <p className="flex items-center gap-1.5 text-sm text-slate-500 mt-2">
                        <Bell className="size-4 shrink-0" aria-hidden />
                        {t('reminderLead', { lead: REMINDER_LEAD_KEYS[plan.reminder_lead_hours] ? t(REMINDER_LEAD_KEYS[plan.reminder_lead_hours]).toLowerCase() : t('leadHours', { count: plan.reminder_lead_hours }).toLowerCase() })}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {/* A sat plan can't be started again — the server rejects
                        it — so the affordance is dropped rather than shown
                        disabled with no explanation. A plan that hasn't
                        opened yet is the opposite case: the button stays,
                        disabled, and says when — otherwise a plan booked for
                        later looks broken. */}
                    {!plan.sat_at && (() => {
                      const isOpen = nowMs >= new Date(plan.scheduled_for).getTime()
                      const busy = startingPlanId === plan.id
                      return (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => void handleStartFromPlan(plan)}
                          disabled={busy || !isOpen}
                          className="border-mode-quizzes text-mode-quizzes hover:bg-mode-quizzes/10"
                        >
                          {busy ? <Loader2 className="size-4 animate-spin mr-1.5" /> : null}
                          {busy
                            ? t('building')
                            : isOpen
                              ? t('startNow')
                              : t('opensAt', { time: formatOpensAt(plan.scheduled_for, locale) })}
                        </Button>
                      )
                    })()}
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => void handleCancelPlan(plan.id)}
                      disabled={cancelingPlanId === plan.id}
                      className="text-slate-500 hover:text-mode-danger hover:bg-red-50"
                    >
                      {cancelingPlanId === plan.id ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <>
                          <Trash2 className="size-4 mr-1.5" />
                          {t('cancel')}
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
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

/** Where a question came from, so a wrong answer points at the place to
 *  reread. The passage is the chunk the generator saw, folded to three lines
 *  until asked for; the link opens the notebook on that very document. A
 *  question whose source was deleted keeps its passage and loses the link. */
function Provenance({
  source,
  excerpt,
}: {
  source: { id: number; title: string; notebook: number } | null
  excerpt: string
}) {
  const t = useTranslations('tests')
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 font-mono text-xs uppercase tracking-wide text-slate-500">
          <BookOpen className="size-3.5" aria-hidden />
          {source ? t('fromSource', { title: source.title }) : t('fromPassage')}
        </p>
        {source && (
          <Link
            href={`/dashboard/notebooks/${source.notebook}?source=${source.id}`}
            className="text-sm font-medium text-mode-library hover:underline"
          >
            {t('openInNotebook')} →
          </Link>
        )}
      </div>
      {excerpt && (
        <>
          <p className={cn('mt-2 text-sm leading-relaxed text-slate-700', !open && 'line-clamp-3')}>
            {excerpt}
          </p>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="mt-1 text-xs text-slate-500 underline underline-offset-4 hover:text-slate-900"
          >
            {open ? t('hidePassage') : t('showPassage')}
          </button>
        </>
      )}
    </div>
  )
}
