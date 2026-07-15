'use client'

import Link from 'next/link'
import { Card } from '@/components/ui/card'
import useSWR from 'swr'
import { analyticsAPI } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  BarChart3,
  BookMarked,
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

type DueCard = {
  id: number
  question: string
  status: 'due' | 'new'
  overdue_days: number
}

/** Why a card is in the queue, in the terms the schedule reasons about. */
function dueRecord(c: DueCard): string {
  if (c.status === 'new') return 'New'
  if (c.overdue_days === 0) return 'Due today'
  return `${c.overdue_days} day${c.overdue_days === 1 ? '' : 's'} overdue`
}

type WeakSource = {
  source_id: number
  title: string
  cards: number
  questions: number
  reviews: number
  accuracy: number | null
}

/** What a document's score rests on — flashcards you graded yourself, quiz
 *  questions the app marked, or both. Empty modes are left out rather than
 *  shown as a zero. */
function sourceRecord(s: WeakSource): string {
  const parts: string[] = []
  if (s.cards) parts.push(`${s.cards} card${s.cards === 1 ? '' : 's'}`)
  if (s.questions) parts.push(`${s.questions} quiz question${s.questions === 1 ? '' : 's'}`)
  parts.push(`${s.reviews} answer${s.reviews === 1 ? '' : 's'}`)
  return parts.join(' · ')
}

export default function AnalyticsPage() {
  const { data: summaryRes } = useSWR(['/analytics/summary'], () => analyticsAPI.getSummary())
  const { data: recsRes, isLoading: recsLoading } = useSWR(
    ['/analytics/recommendations'],
    () => analyticsAPI.getRecommendations({ limit: 5 })
  )

  const summary: Summary | undefined = summaryRes?.data
  const dueCards: DueCard[] = recsRes?.data?.due_cards ?? []
  const weakSources: WeakSource[] = recsRes?.data?.weak_sources ?? []

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
          What to review next, and where you&apos;re weakest — from your own recall record.
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

      {/* Review next — the page's primary action */}
      <Card className="rise border-slate-200 shadow-sheet p-6" style={{ animationDelay: '120ms' }}>
        <div className="flex items-center justify-between gap-3 mb-1">
          <div className="flex items-center gap-2">
            <Target className="size-5 text-mode-flashcards" />
            <h2 className="text-xl font-semibold text-slate-900">Review next</h2>
          </div>
          <Link
            href="/dashboard/flashcards?due=1"
            className="text-sm font-medium text-mode-flashcards hover:underline shrink-0"
          >
            Study these →
          </Link>
        </div>
        <p className="text-sm text-slate-500 mb-4">
          What your review schedule says is owed today. Cards you still know are held
          back until their date comes round.
        </p>

        {recsLoading ? (
          <div className="flex items-center gap-2 text-slate-500 py-6">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </div>
        ) : dueCards.length === 0 ? (
          <p className="text-slate-500 py-6 text-center">
            Nothing due — you&apos;re caught up. New cards appear here as soon as you
            generate them.
          </p>
        ) : (
          <ol className="divide-y divide-slate-100">
            {dueCards.map((c, i) => (
              <li key={c.id} className="flex items-start gap-3 py-3">
                <span className="font-mono text-sm text-slate-400 tabular-nums pt-0.5 shrink-0">
                  {i + 1}
                </span>
                <p className="text-base text-slate-800 flex-1 min-w-0">{c.question}</p>
                <span
                  className={cn(
                    'font-mono text-xs tabular-nums shrink-0 pt-1',
                    c.status === 'due' && c.overdue_days > 0 ? 'text-red-700' : 'text-slate-500'
                  )}
                >
                  {dueRecord(c)}
                </span>
              </li>
            ))}
          </ol>
        )}
      </Card>

      {/* Weakest documents */}
      <Card className="rise border-slate-200 shadow-sheet p-6" style={{ animationDelay: '180ms' }}>
        <div className="flex items-center gap-2 mb-1">
          <FileText className="size-5 text-mode-notebooks" />
          <h2 className="text-xl font-semibold text-slate-900">By document</h2>
        </div>
        <p className="text-sm text-slate-500 mb-4">
          How well you know each document, across flashcards and quizzes together.
          Weakest first.
        </p>

        {weakSources.length === 0 ? (
          <p className="text-slate-500 py-6 text-center">
            Nothing to show yet — upload a source and generate flashcards or a quiz from it.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {weakSources.map((s) => (
              <li key={s.source_id} className="flex items-center gap-4 py-3">
                <div className="flex-1 min-w-0">
                  <p className="text-base text-slate-800 truncate">{s.title}</p>
                  <p className="text-sm text-slate-500">{sourceRecord(s)}</p>
                </div>
                {s.accuracy == null ? (
                  <span className="font-mono text-xs text-slate-600 bg-slate-100 rounded px-2 py-1 shrink-0">
                    Not studied
                  </span>
                ) : (
                  <span className="font-mono text-lg font-semibold text-slate-900 tabular-nums shrink-0">
                    {s.accuracy}%
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
