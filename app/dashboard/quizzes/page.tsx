'use client'

import { Suspense, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import useSWR from 'swr'
import { quizzesAPI } from '@/lib/api'
import { parseSourceIdsParam, hasAllSources } from '@/lib/source-utils'
import { SourceContextBanner } from '@/components/source-context-banner'
import { SourceRequired } from '@/components/source-required'
import { PageHeader } from '@/components/page-header'
import { InPageLanguage, useInPageLanguage } from '@/components/in-page-language'
import { isShort, quizTexts, quizTitle } from '@/lib/translate'
import { useTranslations } from 'next-intl'
import { ArrowRight } from 'lucide-react'

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

function QuizzesStudy() {
  const t = useTranslations('quizzes')
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
    () =>
      [...(quiz?.questions ?? [])].sort((a, b) => a.order - b.order),
    [quiz]
  )

  const [qIndex, setQIndex] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const [score, setScore] = useState(0)
  const [finished, setFinished] = useState(false)
  const [attemptId, setAttemptId] = useState<number | null>(null)
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    setQIndex(0)
    setSelected(null)
    setSubmitted(false)
    setScore(0)
    setFinished(false)
    setAttemptId(null)
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

  // Declared before the early returns so the handlers and the keyboard
  // effect can be too (hooks must run in the same order every render). At
  // runtime this is undefined before the quiz loads; the handlers guard on
  // it. TypeScript narrows it back to Question from the indexed read.
  const question: Question | undefined = questions[qIndex]
  const options =
    question?.question_type === 'true_false' && (!question.options?.length)
      ? ['True', 'False'] // stored values; shown through optionLabel()
      : question?.options ?? []
  // The questions are in the document's language; shown in the page's. The
  // next one is asked for too, so it is ready when it comes.
  const found = useInPageLanguage(question ? quizTexts(question) : [])
  const nextQuestion = questions[qIndex + 1]
  useInPageLanguage(nextQuestion ? quizTexts(nextQuestion) : [])

  const handleSubmit = async () => {
    if (!selected || !attemptId || !question) return
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
  }

  if (!sourceParam || sourceIds.length === 0) {
    return <SourceRequired type="quiz" />
  }

  if (isLoading || starting) {
    return <p className="py-20 text-center text-base text-slate-500">{t('loading')}</p>
  }

  if (!quiz || questions.length === 0) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title={t('title')} />
        <div className="sheet mt-8 flex flex-col items-start gap-5 p-8">
          <p className="max-w-[48ch] text-lg leading-relaxed text-slate-700">{t('noneForSource')}</p>
          <Button asChild>
            <Link href="/dashboard/notebooks">{t('generateFromNotebooks')}</Link>
          </Button>
        </div>
      </div>
    )
  }

  if (finished) {
    const pct = Math.round((score / questions.length) * 100)
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title={t('complete')} />
        <div className="sheet mt-8 flex flex-col items-start gap-6 p-8 md:p-10">
          <p className="font-display text-5xl font-semibold tabular-nums text-slate-900">{pct}%</p>
          <p className="text-lg text-slate-700">{t('scoreLine', { score, total: questions.length, pct })}</p>
          <Button asChild>
            <Link href="/dashboard/notebooks">{t('backToSources')}</Link>
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <Suspense fallback={null}>
        <SourceContextBanner />
      </Suspense>

      <PageHeader
        title={shownTitle(quiz.title, t)}
        meta={t('questionOf', { n: qIndex + 1, total: questions.length })}
      />

      <div className="h-1 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(((qIndex + 1) / questions.length) * 100)}>
        <div
          className="h-full bg-mode transition-[width] duration-300 motion-reduce:transition-none"
          style={{ width: `${((qIndex + 1) / questions.length) * 100}%` }}
        />
      </div>

      <Card className="relative p-8 md:p-10">
        <span className="absolute left-8 -top-px h-[3px] w-12 rounded-b-full bg-mode md:left-10" aria-hidden />
        <p className="mb-8 text-2xl leading-relaxed text-slate-900 md:text-[1.75rem] text-pretty">
          <InPageLanguage text={question.question_text} found={found} />
        </p>

          <div className="space-y-3">
            {options.map((opt) => {
              let style = 'border-slate-200 bg-white hover:bg-slate-50'
              if (submitted) {
                if (opt === question.correct_answer) style = 'border-emerald-400 bg-emerald-50 text-emerald-950'
                else if (opt === selected) style = 'border-red-300 bg-red-50 text-red-950'
              } else if (selected === opt) {
                style = 'border-mode bg-mode/10'
              }
              return (
                <button
                  key={opt}
                  type="button"
                  disabled={submitted}
                  onClick={() => setSelected(opt)}
                  className={`w-full rounded-lg border px-4 py-3 text-left text-lg text-slate-900 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 ${style}`}
                >
                  {opt === 'True' || opt === 'False' ? optionLabel(opt, t) : (
                    <InPageLanguage text={opt} found={found} context={isShort(opt) ? question.question_text : undefined} />
                  )}
                </button>
              )
            })}
          </div>

        {submitted && question.explanation && (
          <p className="mt-6 text-lg text-slate-500 leading-relaxed">
            <InPageLanguage text={question.explanation} found={found} />
          </p>
        )}
      </Card>

      <div className="flex justify-center gap-4">
        {!submitted ? (
          <Button
            size="lg"
            disabled={!selected}
            onClick={handleSubmit}
            className="px-8"
          >
            {t('checkAnswer')}
          </Button>
        ) : (
          <Button size="lg" onClick={handleNext} className="px-8">
            {qIndex >= questions.length - 1 ? t('finish') : t('nextQuestion')}
            <ArrowRight aria-hidden />
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

/** The quiz's name in the page's words; a name the student gave stays as written. */
function shownTitle(title: string, t: (key: string, values?: Record<string, string | number>) => string): string {
  const from = quizTitle(title)
  if (!from) return title
  return 'count' in from ? t('titleFromMany', { count: from.count }) : t('titleFrom', { name: from.name })
}

/** True/false options are stored as the English words the grader compares
 *  against; only their display changes with the language. */
function optionLabel(option: string, t: (key: string) => string): string {
  if (option === 'True') return t('true')
  if (option === 'False') return t('false')
  return option
}
