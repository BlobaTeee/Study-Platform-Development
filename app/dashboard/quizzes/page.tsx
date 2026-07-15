'use client'

import { Suspense, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import useSWR from 'swr'
import { quizzesAPI } from '@/lib/api'
import { parseSourceIdsParam, quizMatchesSourceTag } from '@/lib/source-utils'
import { SourceContextBanner } from '@/components/source-context-banner'
import { SourceRequired } from '@/components/source-required'
import { ArrowRight, BookOpen, CheckCircle2, ChevronLeft } from 'lucide-react'

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
  questions: Question[]
}

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
    return allQuizzes.filter((q) => quizMatchesSourceTag(q.description, sourceIds))
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

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <Suspense fallback={null}>
        <SourceContextBanner />
      </Suspense>

      <div className="rise border-t-[3px] border-mode-quizzes pt-4 flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-quizzes">
            Quiz
          </p>
          <h1 className="font-display text-3xl font-semibold text-slate-900 mt-1">{quiz.title}</h1>
          <p className="font-mono text-sm text-slate-500 mt-1 tabular-nums">
            Question {qIndex + 1} of {questions.length}
          </p>
        </div>
        <Button asChild variant="outline" size="lg" className="text-lg h-11 shrink-0">
          <Link href="/dashboard/notebooks">
            <ChevronLeft className="size-5 mr-1" />
            Sources
          </Link>
        </Button>
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

        {submitted && question.explanation && (
          <p className="mt-6 text-lg text-slate-500 leading-relaxed">{question.explanation}</p>
        )}
      </Card>

      <div className="flex justify-center gap-4">
        {!submitted ? (
          <Button
            size="lg"
            disabled={!selected}
            onClick={handleSubmit}
            className="bg-mode-quizzes hover:bg-mode-quizzes-hover text-white h-12 px-10 text-lg"
          >
            Check answer
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
