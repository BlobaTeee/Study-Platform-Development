'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import useSWR from 'swr'
import { analyticsAPI } from '@/lib/api'
import { cn } from '@/lib/utils'
import { type Due, dueBreakdown, caughtUpMessage } from '@/lib/study-format'
import {
  ArrowRight,
  BarChart3,
  BookMarked,
  BookOpen,
  FileText,
  Loader2,
  Target,
  TrendingUp,
  Zap,
} from 'lucide-react'

type Summary = {
  flashcards_count: number
  quizzes_count: number
  quiz_attempts_completed: number
  average_quiz_score: number | null
  flashcard_reviews: number
  flashcard_correct: number
  flashcard_incorrect: number
  flashcard_accuracy: number | null
}

type WeakNotebook = {
  notebook_id: number
  title: string
  cards: number
  questions: number
  reviews: number
  accuracy: number | null
}

/** What a notebook's score rests on — flashcards you graded yourself, quiz
 *  questions the app marked, or both. Empty modes are left out rather than
 *  shown as a zero. */
function notebookRecord(n: WeakNotebook): string {
  const parts: string[] = []
  if (n.cards) parts.push(`${n.cards} card${n.cards === 1 ? '' : 's'}`)
  if (n.questions) parts.push(`${n.questions} quiz question${n.questions === 1 ? '' : 's'}`)
  parts.push(`${n.reviews} answer${n.reviews === 1 ? '' : 's'}`)
  return parts.join(' · ')
}

export default function AnalyticsPage() {
  const { data: summaryRes } = useSWR(['/analytics/summary'], () => analyticsAPI.getSummary())
  const { data: recsRes, isLoading: recsLoading } = useSWR(
    ['/analytics/recommendations'],
    () => analyticsAPI.getRecommendations()
  )

  const summary: Summary | undefined = summaryRes?.data
  const due: Due = recsRes?.data?.due ?? {
    due: 0,
    overdue: 0,
    new: 0,
    next_date: null,
    next_count: 0,
  }
  const ready = due.due + due.new
  const weakNotebooks: WeakNotebook[] = recsRes?.data?.weak_notebooks ?? []

  const stats = [
    { label: 'Flashcards', value: summary?.flashcards_count ?? '—', icon: BookMarked, color: 'text-mode-flashcards' },
    { label: 'Reviews', value: summary?.flashcard_reviews ?? '—', icon: Zap, color: 'text-mode-flashcards' },
    {
      label: 'Recall accuracy',
      value: summary?.flashcard_accuracy != null ? `${summary.flashcard_accuracy}%` : '—',
      icon: Target,
      color: 'text-mode-analytics',
    },
    {
      label: 'Avg quiz score',
      value: summary?.average_quiz_score != null ? `${summary.average_quiz_score}%` : '—',
      icon: TrendingUp,
      color: 'text-mode-quizzes',
    },
    { label: 'Quizzes taken', value: summary?.quiz_attempts_completed ?? '—', icon: FileText, color: 'text-mode-quizzes' },
  ]

  return (
    <div className="space-y-8 max-w-5xl">
      <div className="rise border-t-[3px] border-mode-analytics pt-4">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-analytics">
          Analytics
        </p>
        <h1 className="font-display text-3xl md:text-4xl font-semibold text-slate-900 mt-1 flex items-center gap-3 text-balance">
          <BarChart3 className="size-8 text-mode-analytics shrink-0" />
          Your progress
        </h1>
        <p className="text-lg text-slate-500 mt-2 text-pretty">
          What your schedule says is due, and where you&apos;re weakest — from your own
          study record.
        </p>
      </div>

      {/* Summary strip: one panel, hairline-divided cells (1px gap over a
          slate backing) — an instrument readout rather than floating tiles. */}
      <dl className="rise grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-100 shadow-sheet" style={{ animationDelay: '60ms' }}>
        {stats.map((stat) => {
          const Icon = stat.icon
          return (
            <div key={stat.label} className="bg-white p-5">
              <dt className="flex items-center gap-2 text-slate-500 text-sm">
                <Icon className={`size-4 ${stat.color} shrink-0`} />
                <span className="truncate">{stat.label}</span>
              </dt>
              <dd className="font-mono text-3xl font-semibold text-slate-900 tabular-nums mt-2">
                {stat.value}
              </dd>
            </div>
          )
        })}
      </dl>

      {/* Review next — the page's one action. A count and a button: there is
          nothing to decide between cards, and showing their questions here would
          be a free look at what you're about to be tested on. */}
      <Card className="rise border-slate-200 shadow-sheet p-6" style={{ animationDelay: '120ms' }}>
        {recsLoading ? (
          <div className="flex items-center gap-2 text-slate-500 py-2">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </div>
        ) : ready === 0 ? (
          <div className="flex items-center gap-3 py-2">
            <Target className="size-5 text-mode-analytics shrink-0" />
            <p className="text-lg text-slate-700">{caughtUpMessage(due)}</p>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-5">
            <div className="flex items-baseline gap-4 min-w-0">
              <span className="font-mono text-5xl font-semibold text-slate-900 tabular-nums">
                {ready}
              </span>
              <div className="min-w-0">
                <p className="text-lg text-slate-900">
                  card{ready === 1 ? '' : 's'} ready to study
                </p>
                <p
                  className={cn(
                    'font-mono text-sm tabular-nums',
                    due.overdue > 0 ? 'text-red-700' : 'text-slate-500'
                  )}
                >
                  {dueBreakdown(due)}
                </p>
              </div>
            </div>
            <Button
              asChild
              size="lg"
              className="bg-mode-flashcards hover:bg-mode-flashcards-hover text-white h-12 px-8 text-lg shrink-0"
            >
              <Link href="/dashboard/flashcards?due=1">
                Study now
                <ArrowRight className="size-5 ml-2" />
              </Link>
            </Button>
          </div>
        )}
      </Card>

      {/* Weakest notebooks. Each row links to its notebook: that is where
          the sources live and where the next set of cards gets generated. */}
      <Card className="rise border-slate-200 shadow-sheet p-6" style={{ animationDelay: '180ms' }}>
        <div className="flex items-center gap-2 mb-1">
          <BookOpen className="size-5 text-mode-notebooks" />
          <h2 className="text-xl font-semibold text-slate-900">By notebook</h2>
        </div>
        <p className="text-sm text-slate-500 mb-4">
          How well you know each notebook, across flashcards and quizzes together.
          Weakest first.
        </p>

        {weakNotebooks.length === 0 ? (
          <p className="text-slate-500 py-6 text-center">
            Nothing to show yet — add a source to a notebook and generate flashcards or a quiz from it.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {weakNotebooks.map((n) => (
              <li key={n.notebook_id}>
                <Link
                  href={`/dashboard/notebooks/${n.notebook_id}`}
                  className="flex items-center gap-4 py-3 -mx-2 px-2 rounded-md hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mode-notebooks"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-base text-slate-800 truncate">{n.title}</p>
                    <p className="text-sm text-slate-500">{notebookRecord(n)}</p>
                  </div>
                  {n.accuracy == null ? (
                    <span className="font-mono text-xs text-slate-600 bg-slate-100 rounded px-2 py-1 shrink-0">
                      Not studied
                    </span>
                  ) : (
                    <span className="font-mono text-lg font-semibold text-slate-900 tabular-nums shrink-0">
                      {n.accuracy}%
                    </span>
                  )}
                  <ArrowRight className="size-4 text-slate-400 shrink-0" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
