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
import { PaperUpload } from '@/components/paper-upload'
import { useConfirm } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'
import { useLocale, useTranslations } from 'next-intl'
import { PageHeader } from '@/components/page-header'
import { WhyWrong } from '@/components/why-wrong'
import { InPageLanguage, useInPageLanguage } from '@/components/in-page-language'
import { isShort, quizTexts } from '@/lib/translate'
import { scoreOutOfTen } from '@/lib/study-format'
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
  ai_explanation?: string
  // An exam-shaped paper's part, what the question is worth and (after
  // submit) what it earned; a true/false question's statements, with their
  // answers only after submit; a written answer's grade and model answer.
  section?: ExamSection
  statements?: { label: string; text: string; answer?: boolean }[]
  points?: number
  earned?: number | null
  grade?: { verdict?: string; met?: number[]; detail?: string; not_graded?: boolean }
  solution?: string[]
  // A real paper's figures, cut from its pages.
  figures?: (string | null)[]
}

type ExamSection = 'choice' | 'true_false' | 'short' | 'written'
/** Every sitting is "mixed": its parts are drawn afresh each time
 *  (backend/quizzes/services/exam.py mixed_parts), always out of 10. */
type ExamTemplate = 'mixed'

type MockTest = {
  id: number
  deadline: string
  duration_minutes: number
  question_count: number
  notebook_title: string
  paper: PaperQuestion[]
  template?: string
  short_paper?: boolean
  missing_parts?: ExamSection[]
  // Present on GET but not on the start response's shape we rely on; used
  // only to detect "this test is already finished" on resume.
  completed_at?: string | null
  score?: number | null
}

type SubmitResult = {
  id: number
  // Null for a real paper the student brought, which belongs to no notebook.
  notebook: number | null
  score: number
  completed_at: string
  question_count: number
  correct_count: number
  // Size of the notebook's mistake bank after this sitting was marked.
  mistake_count: number
  paper: PaperQuestion[]
  template?: string
  parts?: { section: ExamSection; count: number; points: number; earned: number }[]
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
  const nav = useTranslations('nav')
  const locale = useLocale()
  const router = useRouter()
  const searchParams = useSearchParams()
  const idParam = searchParams.get('id')

  const { data: nbData, isLoading: notebooksLoading } = useSWR(['/notebooks/'], () =>
    notebooksAPI.getNotebooks()
  )
  const notebooks: NotebookItem[] = nbData?.data?.results ?? nbData?.data ?? []

  const [notebookId, setNotebookId] = useState<number | ''>('')
  const [starting, setStarting] = useState(false)
  const [confirm, confirmDialog] = useConfirm()
  const [setupError, setSetupError] = useState('')
  // Keyed by notebook so a count fetched for the previous pick never shows
  // under the new one; `mistakeCount` below is null until this one's arrives.
  const [bank, setBank] = useState<{ notebook: number; count: number } | null>(null)
  const mistakeCount = bank && bank.notebook === notebookId ? bank.count : null

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

  // The paper is in the documents' language; shown in the page's. Sitting:
  // this question and the next. Review: the whole paper.
  const found = useInPageLanguage(
    result
      ? result.paper.flatMap(examTexts)
      : [paper[qIndex], paper[qIndex + 1]].flatMap((q) => (q ? examTexts(q) : []))
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
  }, [test, t])

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
      duration_minutes?: number
      planned_test?: number
      mistakes_only?: boolean
      template?: ExamTemplate
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
    setStarting(true)
    setSetupError('')
    try {
      await beginTest({ notebook: Number(notebookId), template: 'mixed' })
    } catch (err) {
      setSetupError(apiErrorMessage(err, t('startFailed')))
    } finally {
      setStarting(false)
    }
  }

  // A notebook's missed questions are redone like a quiz, marked one by
  // one, not sat as another timed paper.
  const handleRetakeMistakes = (notebook: number) => router.push(`/dashboard/quizzes/redo?notebook=${notebook}`)

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
    [test, handleSubmit, t]
  )

  // Typing changes the answer here; it is saved when the box loses focus,
  // so a written answer is not sent to the server on every keystroke.
  const typeAnswer = useCallback((question: PaperQuestion, text: string) => {
    setAnswers((prev) => ({ ...prev, [question.id]: text }))
  }, [])

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
      // Arrows and digits belong to the box while an answer is being typed.
      const target = e.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return
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
        <PageHeader
          title={t('reviewed')}
          meta={`${result.correct_count} / ${result.question_count}`}
          action={
            <Button variant="outline" onClick={handleNewTest}>
              <ChevronLeft aria-hidden />
              {t('newTest')}
            </Button>
          }
        />

        {/* The score, then the bank - not just this paper's misses: a
            question cleared today drops out, one missed last week and again
            today is still one. */}
        <div className="sheet flex flex-wrap items-center gap-x-8 gap-y-4 p-6 md:p-8">
          <p className="font-display text-5xl font-semibold tabular-nums text-slate-900">
            {result.template ? t('scoreOutOf10', { score: scoreOutOfTen(result.score, locale) }) : `${pct}%`}
          </p>
          <p className="min-w-0 flex-1 basis-64 text-base text-slate-700">
            {result.mistake_count === 0
              ? t('bankClear')
              : result.notebook === null
                ? t('paperMistakes', { count: result.mistake_count })
                : t('mistakesAfterTest', { count: result.mistake_count })}
          </p>
          {/* A brought paper's misses stay in this review (no notebook to redo them from). */}
          {result.mistake_count > 0 && result.notebook !== null && (
            <Button variant="tinted" onClick={() => handleRetakeMistakes(result.notebook!)}>
              {t('retakeMistakes')}
            </Button>
          )}
          {setupError && <p className="basis-full text-sm text-red-700">{setupError}</p>}
          {/* Where the points went, part by part, as the exam would report them. */}
          {(result.parts ?? []).length > 0 && (
            <ul className="basis-full grid gap-2 sm:grid-cols-3">
              {(result.parts ?? []).map((part) => (
                <li key={part.section} className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-sm text-slate-600">{t(`part_${part.section}`)}</p>
                  <p className="font-mono text-lg tabular-nums text-slate-900">
                    {formatPoints(part.earned, locale)}<span className="text-slate-500">/{formatPoints(part.points, locale)}</span>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-5">
          {reviewPaper.map((q, i) => (
            <Card
              key={q.id}
              className="p-6 md:p-8"
            >
              <div className="mb-4 flex items-start gap-3">
                <span className="shrink-0 font-mono text-sm text-slate-500 tabular-nums">{i + 1}</span>
                {q.is_correct ? (
                  <CheckCircle2 className="size-5 text-emerald-600 shrink-0 mt-0.5" aria-hidden />
                ) : (
                  <XCircle className="size-5 text-red-600 shrink-0 mt-0.5" aria-hidden />
                )}
                <p className="text-lg text-slate-900 leading-relaxed">
                  {result.template && q.section && (
                    <span className="mr-2 text-sm font-medium text-mode-ink">{t(`part_${q.section}`)}</span>
                  )}
                  <InPageLanguage text={q.question_text} found={found} math={!!result.template} figures={q.figures} />
                </p>
              </div>

              {q.section && q.section !== 'choice' ? (
                <ExamReview question={q} found={found} />
              ) : (
              <div className="space-y-2 mb-4">
                {(q.options ?? []).map((opt) => {
                  let style = 'border-slate-200 bg-white text-slate-700'
                  if (opt === q.correct_answer) style = 'border-emerald-400 bg-emerald-50 text-emerald-900'
                  else if (opt === q.user_answer) style = 'border-red-300 bg-red-50 text-red-900'
                  return (
                    <div key={opt} className={`rounded-lg border-2 px-4 py-2.5 text-base ${style}`}>
                      <InPageLanguage text={opt} found={found} math={!!result.template} context={isShort(opt) ? q.question_text : undefined} />
                      {opt === q.correct_answer && (
                        <span className="ml-2 text-sm font-medium text-emerald-700">{t('correctAnswer')}</span>
                      )}
                      {opt === q.user_answer && opt !== q.correct_answer && (
                        <span className="ml-2 text-sm font-medium text-red-700">{t('yourAnswer')}</span>
                      )}
                    </div>
                  )
                })}
                {!q.user_answer && (
                  <p className="text-sm text-slate-500 italic">{t('leftUnanswered')}</p>
                )}
              </div>
              )}

              {q.explanation && (
                <p className="text-base text-slate-500 leading-relaxed">
                  <InPageLanguage text={q.explanation} found={found} />
                </p>
              )}
              {!q.is_correct && q.section !== 'true_false' && q.section !== 'written' && (
                <WhyWrong testId={result.id} paperQuestionId={q.id} initial={q.ai_explanation} />
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
        <PageHeader
          title={test.notebook_title}
          meta={t('questionOf', { n: qIndex + 1, total: paper.length, answered: answeredCount })}
          action={
            <div
              className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 ${
                low ? 'border-red-300 bg-red-50 text-red-800' : 'border-slate-300 bg-white text-slate-900'
              }`}
              role="timer"
              aria-live="polite"
              title={t('timeRemaining')}
            >
              <Clock className="size-4" aria-hidden />
              <span className="font-mono text-lg font-semibold tabular-nums">
                {secondsRemaining !== null ? formatClock(secondsRemaining) : '--:--'}
              </span>
              <span className="sr-only">{t('timeRemaining')}</span>
            </div>
          }
        />

        {test.short_paper && (
          <p className="text-sm text-slate-600">
            {t('shortPaper', { questions: common('questions', { count: test.question_count }) })}
          </p>
        )}

        <div className="h-1 overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full bg-mode transition-[width] duration-300 motion-reduce:transition-none"
            style={{ width: `${((qIndex + 1) / Math.max(1, paper.length)) * 100}%` }}
          />
        </div>

        {/* Question palette: jump to any question, answered ones marked so
            no state is carried by colour alone. */}
        <div className="flex flex-wrap gap-2">
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
                className={`size-9 rounded-md border font-mono text-sm tabular-nums transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 ${
                  isCurrent
                    ? 'border-mode bg-mode text-white'
                    : isAnswered
                      ? 'border-mode/40 bg-mode/10 text-mode-ink'
                      : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
                }`}
              >
                {i + 1}
              </button>
            )
          })}
        </div>

        {question && (
          <Card className="relative p-8 md:p-10">
            <span className="absolute left-8 -top-px h-[3px] w-12 rounded-b-full bg-mode md:left-10" aria-hidden />
            <div className="mb-6 flex items-center gap-3">
              <span className="font-mono text-sm text-slate-500 tabular-nums">
                Q{String(qIndex + 1).padStart(2, '0')}
              </span>
              {test.template && question.section && (
                <span className="text-sm font-medium text-mode-ink">
                  {t(`part_${question.section}`)} · {t('pointsWorth', { points: formatPoints(question.points ?? 0, locale), n: question.points ?? 0 })}
                </span>
              )}
              <span className="h-px flex-1 bg-slate-100" aria-hidden />
            </div>
            {/* A short question reads large; a real paper's long one at reading size (2026-11-26). */}
            <p className={cn('mb-8 leading-relaxed text-slate-900',
                             question.question_text.length > 140 ? 'text-lg md:text-xl' : 'text-xl md:text-2xl')}>
              <InPageLanguage text={question.question_text} found={found} math={!!test.template} figures={question.figures} />
            </p>

            {question.section && question.section !== 'choice' && (
              <ExamAnswer
                question={question}
                value={answers[question.id] ?? ''}
                onType={(text) => typeAnswer(question, text)}
                onSave={(text) => void selectAnswer(question, text)}
                found={found}
              />
            )}

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
                      isSelected ? 'border-mode bg-mode/10' : 'border-slate-200 bg-white hover:bg-slate-50'
                    }`}
                  >
                    <InPageLanguage text={opt} found={found} math={!!test.template} context={isShort(opt) ? question.question_text : undefined} />
                  </button>
                )
              })}
            </div>
          </Card>
        )}

        {saveError && (
          <p role="alert" className="text-center text-sm text-red-700">
            {saveError}
          </p>
        )}

        {submitError && (
          <div role="alert" className="flex flex-col items-center gap-3 text-center">
            <p className="text-sm text-red-700">{submitError}</p>
            <Button variant="tinted" size="sm" onClick={() => void handleSubmit()}>
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
          >
            <ArrowLeft className="size-5 mr-2" />
            {t('previous')}
          </Button>
          {qIndex < paper.length - 1 ? (
            <Button
              size="lg"
              onClick={goNext}
              className="px-8"
            >
              {t('nextQuestion')}
              <ArrowRight className="size-5 ml-2" />
            </Button>
          ) : null}
          <Button variant="tinted" size="lg" onClick={handleSubmitClick} disabled={submitting}>
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
      <PageHeader title={nav('tests')} />

      <p className="text-base text-slate-500 leading-relaxed">{t('sitLead')}</p>

      {notebooksLoading ? (
        <p className="text-lg text-slate-500 text-center py-12">{t('loadingNotebooks')}</p>
      ) : notebooks.length === 0 ? (
        <div className="text-center py-16 max-w-md mx-auto">
          <BookOpen className="size-16 text-slate-300 mx-auto mb-4" />
          <p className="text-xl text-slate-600 mb-6">{t('noNotebooks')}</p>
          <Button asChild size="lg">
            <Link href="/dashboard/notebooks">{t('goToNotebooks')}</Link>
          </Button>
        </div>
      ) : (
        <Card className="p-6 md:p-8">
          <form onSubmit={handleStart} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="test-notebook">{t('notebook')}</Label>
              <select
                id="test-notebook"
                value={notebookId}
                onChange={(e) => setNotebookId(Number(e.target.value))}
                className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 outline-none focus-visible:border-mode focus-visible:ring-[3px] focus-visible:ring-mode/25"
              >
                {notebooks.map((nb) => (
                  <option key={nb.id} value={nb.id}>
                    {nb.title}
                  </option>
                ))}
              </select>
            </div>

            {/* No format to pick: each sitting draws its own mix of parts, so
                two papers are never the same shape. */}
            <p className="text-base text-slate-700">{t('mixedLead')}</p>

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
              className="w-full"
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

            {/* What is owed lives in "Cần ôn" on the Progress page; here, only a pointer to it. */}
            {mistakeCount !== null && mistakeCount > 0 && (
              <p className="border-t border-slate-200 pt-4 text-sm text-slate-600">
                {t('mistakesWaiting', { count: mistakeCount })}{' · '}
                <Link href="/dashboard/analytics#review-title" className="font-medium text-slate-900 underline underline-offset-4 hover:text-mode">
                  {t('seeReviewList')}
                </Link>
              </p>
            )}
          </form>
        </Card>
      )}

      <PaperUpload onStart={(id) => router.replace(`/dashboard/tests?id=${id}`)} />

      <div className="space-y-6 border-t border-slate-200 pt-8">
        <div>
          <h2 className="font-display text-2xl font-semibold text-slate-900">{t('planAhead')}</h2>
          <p className="text-base text-slate-500 mt-2 leading-relaxed">
            {t('planLead')}
          </p>
        </div>

        {notebooks.length > 0 && (
          <Card className="p-6 md:p-8">
            <form onSubmit={handleCreatePlan} className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="plan-notebook">{t('notebook')}</Label>
                <select
                  id="plan-notebook"
                  value={planNotebookId}
                  onChange={(e) => setPlanNotebookId(Number(e.target.value))}
                  className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 outline-none focus-visible:border-mode focus-visible:ring-[3px] focus-visible:ring-mode/25"
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
                    className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 outline-none focus-visible:border-mode focus-visible:ring-[3px] focus-visible:ring-mode/25"
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
                className="w-full"
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
                    <p className="mt-1 text-sm text-slate-600">
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
                          variant="tinted"
                          size="sm"
                          onClick={() => void handleStartFromPlan(plan)}
                          disabled={busy || !isOpen}
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
        <p className="flex items-center gap-1.5 text-sm font-medium text-slate-600">
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

/** What to translate for one question: the quiz texts, and an exam part's statements, model answer and feedback. */
function examTexts(q: PaperQuestion) {
  return [...quizTexts(q), ...(q.statements ?? []).map((st) => st.text), ...(q.solution ?? []), q.grade?.detail]
}

/** Points the way the exam writes them: "0,25" in Vietnamese, "0.25" in English. */
function formatPoints(points: number, locale: string): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(points)
}

/** A true/false mark kept as JSON {label: bool}; anything else is no marks. */
function readMarks(value: string): Record<string, boolean> {
  try {
    const data = JSON.parse(value || '{}')
    return data && typeof data === 'object' ? data : {}
  } catch {
    return {}
  }
}

/** The answer box of an exam part that is not multiple choice: True/False
 *  per statement (saved on each press), or a typed answer (saved when the
 *  box loses focus). */
function ExamAnswer({ question, value, onType, onSave, found }: {
  question: PaperQuestion
  value: string
  onType: (text: string) => void
  onSave: (text: string) => void
  found: Map<string, string> | undefined
}) {
  const t = useTranslations('tests')
  if (question.section === 'true_false') {
    const marks = readMarks(value)
    return (
      <ul className="divide-y divide-slate-200 rounded-xl border-2 border-slate-200">
        {(question.statements ?? []).map((st) => (
          <li key={st.label} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:gap-4">
            <p className="min-w-0 flex-1 text-lg leading-relaxed text-slate-900">
              <span className="mr-2 font-medium text-slate-600">{st.label})</span>
              <InPageLanguage text={st.text} found={found} math />
            </p>
            <div role="group" aria-label={`${st.label})`} className="flex shrink-0 gap-2">
              {[true, false].map((mark) => (
                <button
                  key={String(mark)}
                  type="button"
                  aria-pressed={marks[st.label] === mark}
                  onClick={() => onSave(JSON.stringify({ ...marks, [st.label]: mark }))}
                  className={`h-10 min-w-20 rounded-lg border-2 px-3 text-base font-medium transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 ${
                    marks[st.label] === mark ? 'border-mode bg-mode text-white' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {mark ? t('markTrue') : t('markFalse')}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ul>
    )
  }
  if (question.section === 'short') {
    return (
      <div className="max-w-md space-y-2">
        <label htmlFor={`exam-${question.id}`} className="text-sm font-medium text-slate-700">{t('shortLabel')}</label>
        <input
          id={`exam-${question.id}`}
          value={value}
          autoComplete="off"
          maxLength={200}
          onChange={(e) => onType(e.target.value)}
          onBlur={(e) => onSave(e.target.value)}
          className="h-12 w-full rounded-xl border-2 border-slate-200 bg-white px-4 text-lg text-slate-900 outline-none focus-visible:border-mode focus-visible:ring-[3px] focus-visible:ring-mode/30"
        />
      </div>
    )
  }
  return (
    <div className="space-y-2">
      <label htmlFor={`exam-${question.id}`} className="text-sm font-medium text-slate-700">{t('writtenLabel')}</label>
      <textarea
        id={`exam-${question.id}`}
        value={value}
        rows={10}
        maxLength={4000}
        onChange={(e) => onType(e.target.value)}
        onBlur={(e) => onSave(e.target.value)}
        placeholder={t('writtenPlaceholder')}
        className="block w-full resize-y rounded-xl border-2 border-slate-200 bg-white px-4 py-3 text-base leading-relaxed text-slate-900 outline-none placeholder:text-slate-500 focus-visible:border-mode focus-visible:ring-[3px] focus-visible:ring-mode/30"
      />
    </div>
  )
}

/** The review of an exam part that is not multiple choice: each statement
 *  with its answer and the student's mark, the typed answer beside the
 *  expected one, or the written answer with its feedback and model answer. */
function ExamReview({ question, found }: { question: PaperQuestion; found: Map<string, string> | undefined }) {
  const t = useTranslations('tests')
  const locale = useLocale()
  const worth = (
    <p className="text-sm text-slate-600">
      {t('partScore', { earned: formatPoints(question.earned ?? 0, locale), points: formatPoints(question.points ?? 0, locale) })}
    </p>
  )
  if (question.section === 'true_false') {
    const marks = readMarks(question.user_answer ?? '')
    return (
      <div className="mb-4 space-y-3">
        <ul className="space-y-2">
          {(question.statements ?? []).map((st) => {
            const mine = marks[st.label]
            const right = mine === st.answer
            return (
              <li key={st.label} className={`flex gap-3 rounded-lg border-2 px-4 py-2.5 text-base ${
                right ? 'border-emerald-300 bg-emerald-50' : 'border-red-300 bg-red-50'
              }`}>
                <span className="w-12 shrink-0 font-medium text-slate-900">{st.answer ? t('markTrue') : t('markFalse')}</span>
                <span className="min-w-0 flex-1 text-slate-800">
                  {st.label}) <InPageLanguage text={st.text} found={found} math />
                  {!right && (
                    <span className="ml-2 text-sm text-red-700">
                      · {typeof mine === 'boolean' ? `${t('yourAnswer')}: ${mine ? t('markTrue') : t('markFalse')}` : t('leftUnanswered')}
                    </span>
                  )}
                </span>
              </li>
            )
          })}
        </ul>
        {worth}
      </div>
    )
  }
  if (question.section === 'short') {
    return (
      <div className="mb-4 space-y-1.5 text-base">
        <p className="text-slate-800">
          <span className="text-slate-600">{t('yourAnswer')}: </span>
          {question.user_answer ? question.user_answer : <span className="italic text-slate-500">{t('leftUnanswered')}</span>}
        </p>
        <p className="text-emerald-800">
          <span className="text-slate-600">{t('correctAnswer')}: </span>
          <InPageLanguage text={question.correct_answer ?? ''} found={found} math />
        </p>
        {worth}
      </div>
    )
  }
  const grade = question.grade ?? {}
  return (
    <div className="mb-4 space-y-4">
      <div>
        <p className="text-sm font-medium text-slate-600">{t('yourAnswer')}</p>
        {question.user_answer ? (
          <p className="mt-1 whitespace-pre-wrap text-base leading-relaxed text-slate-800">{question.user_answer}</p>
        ) : (
          <p className="mt-1 text-sm italic text-slate-500">{t('leftUnanswered')}</p>
        )}
      </div>
      {grade.not_graded ? (
        <p className="text-sm text-amber-800">{t('notGraded')}</p>
      ) : grade.detail ? (
        <p className="text-base text-slate-800"><InPageLanguage text={grade.detail} found={found} math /></p>
      ) : null}
      {worth}
      {(question.solution ?? []).length > 0 && (
        <div>
          <p className="text-sm font-medium text-slate-600">{t('modelAnswer')}</p>
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-base leading-relaxed text-slate-800">
            {(question.solution ?? []).map((step, i) => (
              <li key={i}><InPageLanguage text={step} found={found} math /></li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}
