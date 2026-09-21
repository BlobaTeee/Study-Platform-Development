'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/page-header'
import useSWR from 'swr'
import { analyticsAPI } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useLocale, useTranslations } from 'next-intl'
import { type Due, caughtUpMessage } from '@/lib/study-format'
import { ActivityStrip, type ActivityDay, type ActivitySummary } from '@/components/activity-strip'
import { ArrowRight } from 'lucide-react'

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
    <div className="space-y-8">
      <PageHeader title={t('title')} lead={t('lead')} />

      {/* One instrument panel: fourteen days on top, what is owed as one
          line under it, then the notebooks. Hairlines, not tiles. */}
      <div className="sheet">
        {/* Fourteen days, one column each. Replaces the lifetime-total tiles
            that used to sit here: those never changed from one visit to the
            next, and could not answer "am I getting anywhere?" */}
        <section className="p-6 md:p-8">
          {activityDays.length === 0 ? (
            <div className="h-40 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none" aria-busy />
          ) : (
            <ActivityStrip days={activityDays} summary={activitySummary} />
          )}
        </section>

        {/* Review next: the page's one action. A count and a button - showing
            the cards here would be a free look at what you're about to be
            tested on. */}
        <section data-mode="flashcards" className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-t border-slate-200 px-6 py-5 md:px-8">
          {recsLoading ? (
            <div className="h-6 w-64 animate-pulse rounded bg-slate-100 motion-reduce:animate-none" aria-busy />
          ) : ready === 0 ? (
            <p className="text-base text-slate-700">{caughtUpMessage(due, common, locale)}</p>
          ) : (
            <>
              <p className="min-w-0 text-base text-slate-900">
                <span className="font-mono text-2xl font-semibold tabular-nums">{ready}</span>{' '}
                {t('readyToStudy', { count: ready })}
                {due.overdue > 0 && (
                  <span className="ml-2 text-sm text-red-700">{common('overdueCount', { count: due.overdue })}</span>
                )}
              </p>
              <Button asChild>
                <Link href="/dashboard/flashcards?due=1">
                  {t('studyNow')}
                  <ArrowRight aria-hidden />
                </Link>
              </Button>
            </>
          )}
        </section>

        {/* Weakest notebooks. Each row links to its notebook: that is where
            the sources live and where the next set of cards gets generated. */}
        <section data-mode="library" className="border-t border-slate-200 p-6 md:p-8">
          <h2 className="text-base font-semibold text-slate-900">{t('byNotebook')}</h2>
          <p className="mt-1 text-sm text-slate-600">{t('byNotebookLead')}</p>

          {weakNotebooks.length === 0 ? (
            <p className="py-6 text-slate-600">{t('byNotebookEmpty')}</p>
          ) : (
            <ul className="mt-3 divide-y divide-slate-100">
              {weakNotebooks.map((n) => (
                <li key={n.notebook_id}>
                  <Link
                    href={`/dashboard/notebooks/${n.notebook_id}`}
                    className="-mx-2 flex items-center gap-4 rounded-md px-2 py-3 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-base text-slate-900">{n.title}</p>
                      <p className="text-sm text-slate-600">{notebookRecord(n, t, common)}</p>
                    </div>
                    {n.accuracy == null ? (
                      <span className="shrink-0 text-sm text-slate-500">{common('notStudied')}</span>
                    ) : (
                      <span className="flex shrink-0 items-center gap-3">
                        <span className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-100" aria-hidden>
                          <span
                            className={cn('block h-full rounded-full', n.accuracy >= 70 ? 'bg-mode-analytics' : n.accuracy >= 40 ? 'bg-mode-flashcards' : 'bg-red-400')}
                            style={{ width: `${Math.max(4, Math.min(100, n.accuracy))}%` }}
                          />
                        </span>
                        <span className="w-12 text-right font-mono text-base tabular-nums text-slate-900">{n.accuracy}%</span>
                      </span>
                    )}
                    <ArrowRight className="size-4 shrink-0 text-slate-400" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
