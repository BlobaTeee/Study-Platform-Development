'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import useSWR from 'swr'
import { analyticsAPI } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useLocale, useTranslations } from 'next-intl'
import { type Due, dueBreakdown, caughtUpMessage } from '@/lib/study-format'
import { ActivityStrip, type ActivityDay, type ActivitySummary } from '@/components/activity-strip'
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  Loader2,
  Target,
} from 'lucide-react'

type WeakNotebook = {
  notebook_id: number
  title: string
  cards: number
  questions: number
  reviews: number
  accuracy: number | null
}

type T = (key: string, values?: Record<string, string | number>) => string

/** What a notebook's score rests on — flashcards you graded yourself, quiz
 *  questions the app marked, or both. Empty modes are left out rather than
 *  shown as a zero. */
function notebookRecord(n: WeakNotebook, t: T, common: T): string {
  const parts: string[] = []
  if (n.cards) parts.push(common('cards', { count: n.cards }))
  if (n.questions) parts.push(t('quizQuestions', { count: n.questions }))
  parts.push(t('answers', { count: n.reviews }))
  return parts.join(' · ')
}

export default function AnalyticsPage() {
  const t = useTranslations('analytics')
  const common = useTranslations('common')
  const locale = useLocale()
  const { data: recsRes, isLoading: recsLoading } = useSWR(
    ['/analytics/recommendations'],
    () => analyticsAPI.getRecommendations()
  )
  const { data: activityRes } = useSWR(['/analytics/activity'], () => analyticsAPI.getActivity())
  const activityDays: ActivityDay[] = activityRes?.data?.days ?? []
  const activitySummary: ActivitySummary = activityRes?.data?.summary ?? {
    reviews: 0,
    accuracy: null,
    mock_tests: 0,
  }
  const due: Due = recsRes?.data?.due ?? {
    due: 0,
    overdue: 0,
    new: 0,
    next_date: null,
    next_count: 0,
  }
  const ready = due.due + due.new
  const weakNotebooks: WeakNotebook[] = recsRes?.data?.weak_notebooks ?? []

  return (
    <div className="space-y-8 max-w-5xl">
      <div className="rise border-t-[3px] border-mode-analytics pt-4">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-analytics">
          {t('eyebrow')}
        </p>
        <h1 className="font-display text-3xl md:text-4xl font-semibold text-slate-900 mt-1 flex items-center gap-3 text-balance">
          <BarChart3 className="size-8 text-mode-analytics shrink-0" />
          {t('title')}
        </h1>
        <p className="text-lg text-slate-500 mt-2 text-pretty">
          {t('lead')}
        </p>
      </div>

      {/* Fourteen days, one column each. Replaces the lifetime-total tiles
          that used to sit here: those never changed from one visit to the
          next, and could not answer "am I getting anywhere?" */}
      <Card className="rise border-slate-200 shadow-sheet p-6" style={{ animationDelay: '60ms' }}>
        {activityDays.length === 0 ? (
          <div className="flex items-center gap-2 text-slate-500 py-2">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </div>
        ) : (
          <ActivityStrip days={activityDays} summary={activitySummary} />
        )}
      </Card>

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
            <p className="text-lg text-slate-700">{caughtUpMessage(due, common, locale)}</p>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-5">
            <div className="flex items-baseline gap-4 min-w-0">
              <span className="font-mono text-5xl font-semibold text-slate-900 tabular-nums">
                {ready}
              </span>
              <div className="min-w-0">
                <p className="text-lg text-slate-900">
                  {t('readyToStudy', { count: ready })}
                </p>
                <p
                  className={cn(
                    'font-mono text-sm tabular-nums',
                    due.overdue > 0 ? 'text-red-700' : 'text-slate-500'
                  )}
                >
                  {dueBreakdown(due, common)}
                </p>
              </div>
            </div>
            <Button
              asChild
              size="lg"
              className="bg-mode-flashcards hover:bg-mode-flashcards-hover text-white h-12 px-8 text-lg shrink-0"
            >
              <Link href="/dashboard/flashcards?due=1">
                {t('studyNow')}
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
          <h2 className="text-xl font-semibold text-slate-900">{t('byNotebook')}</h2>
        </div>
        <p className="text-sm text-slate-500 mb-4">
          {t('byNotebookLead')}
        </p>

        {weakNotebooks.length === 0 ? (
          <p className="text-slate-500 py-6 text-center">
            {t('byNotebookEmpty')}
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
                    <p className="text-sm text-slate-500">{notebookRecord(n, t, common)}</p>
                  </div>
                  {n.accuracy == null ? (
                    <span className="font-mono text-xs text-slate-600 bg-slate-100 rounded px-2 py-1 shrink-0">
                      {common('notStudied')}
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
