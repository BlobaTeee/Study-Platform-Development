'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/page-header'
import useSWR from 'swr'
import { analyticsAPI, reviewsAPI, type ForgottenNotebook, type MisconceptionNotebook, type NotebookForecast } from '@/lib/api'
import { ForgottenCards } from '@/components/forgotten-cards'
import { Misconceptions } from '@/components/misconceptions'
import { cn } from '@/lib/utils'
import { useLocale, useTranslations } from 'next-intl'
import { type Due, caughtUpMessage, MASTERY_LABEL, masteryBarClass, masteryLevel } from '@/lib/study-format'
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
  return parts.join(' · ')
}

/** The test-day forecast in one phrase, for the notebook's line. Counts are
 *  expected values from the memory model, so they are rounded. */
function forecastPhrase(f: NotebookForecast, t: T): string {
  const values = { now: Math.round(f.now), studied: f.studied, later: Math.round(f.at_exam), days: f.days_ahead }
  return t(f.has_exam ? 'forecastShortExam' : 'forecastShortWeek', values)
}

/** The review that raises the forecast most, when it raises it at all. */
function worthReviewing(f: NotebookForecast | undefined): f is NotebookForecast {
  return !!f && f.suggestion.card_ids.length > 0 && Math.round(f.suggestion.at_exam) > Math.round(f.at_exam)
}

export default function AnalyticsPage() {
  const t = useTranslations('analytics')
  const nav = useTranslations('nav')
  const common = useTranslations('common')
  const home = useTranslations('home')
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
  // Today's share, as on the home page: the two pages must not disagree, and
  // the whole debt is the number that makes starting feel pointless.
  const ready = due.today ?? due.due + due.new
  const weakNotebooks: WeakNotebook[] = recsRes?.data?.weak_notebooks ?? []
  const { data: forgottenRes, isLoading: forgottenLoading } = useSWR(
    ['/study/forgotten-groups'],
    () => reviewsAPI.getForgottenGroups()
  )
  const forgotten: ForgottenNotebook[] = forgottenRes?.data?.notebooks ?? []
  // Finding mix-ups is a model request the server runs on its own: while it
  // is under way the answer says so, and the page looks again shortly.
  const { data: mixUpsRes, isLoading: mixUpsLoading } = useSWR(
    ['/quizzes/misconceptions'],
    () => reviewsAPI.getMisconceptions(),
    { refreshInterval: (latest) => (latest?.data?.pending ? 8000 : 0) }
  )
  const mixUps: MisconceptionNotebook[] = mixUpsRes?.data?.notebooks ?? []
  const mixUpsPending = !!mixUpsRes?.data?.pending
  const { data: forecastRes } = useSWR(['/study/forecast'], () => reviewsAPI.getForecast())
  const forecast: NotebookForecast[] = forecastRes?.data?.notebooks ?? []
  const forecastOf = new Map(forecast.map((f) => [f.notebook_id, f]))
  const anyReview = weakNotebooks.some((n) => worthReviewing(forecastOf.get(n.notebook_id)))

  return (
    <div className="space-y-8">
      <PageHeader title={nav('analytics')} />

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
                {due.overdue > 0 && !due.later && (
                  <span className="ml-2 text-sm text-red-700">{common('overdueCount', { count: due.overdue })}</span>
                )}
                {due.later ? (
                  <span className="mt-1 block text-sm text-slate-600">{home('laterCount', { count: due.later })}</span>
                ) : null}
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

        {/* Cards last answered wrong, by notebook and then by idea.
            Relearning a group together works better than meeting the same
            idea scattered through a mixed queue. */}
        <section data-mode="flashcards" aria-labelledby="forgotten-title" className="border-t border-slate-200 p-6 md:p-8">
          <h2 id="forgotten-title" className="text-base font-semibold text-slate-900">{t('forgottenTitle')}</h2>
          <p className="mt-1 max-w-[65ch] text-sm text-slate-600">{t('forgottenLead')}</p>

          {forgottenLoading ? (
            <div className="mt-4 h-24 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none" aria-busy />
          ) : forgotten.length === 0 ? (
            <p className="max-w-[65ch] py-6 text-slate-600">{t('forgottenEmpty')}</p>
          ) : (
            <ForgottenCards notebooks={forgotten} />
          )}
        </section>

        {/* What the student keeps confusing, read from the wrong options
            they chose in more than one question. */}
        <section data-mode="quizzes" aria-labelledby="mixups-title" className="border-t border-slate-200 p-6 md:p-8">
          <h2 id="mixups-title" className="text-base font-semibold text-slate-900">{t('mixUpsTitle')}</h2>
          <p className="mt-1 max-w-[65ch] text-sm text-slate-600">{t('mixUpsLead')}</p>
          {mixUpsLoading ? (
            <div className="mt-4 h-20 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none" aria-busy />
          ) : mixUps.length === 0 ? (
            <p className="max-w-[65ch] py-6 text-slate-600">{t(mixUpsPending ? 'mixUpsPending' : 'mixUpsEmpty')}</p>
          ) : (
            <>
              <Misconceptions notebooks={mixUps} />
              {mixUpsPending && <p className="mt-2 text-sm text-slate-500">{t('mixUpsPendingMore')}</p>}
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
              {weakNotebooks.map((n) => {
                const f = forecastOf.get(n.notebook_id)
                return (
                  <li key={n.notebook_id} className="flex flex-col sm:flex-row sm:items-center sm:gap-3">
                    <Link
                      href={`/dashboard/notebooks/${n.notebook_id}`}
                      className="-mx-2 flex min-w-0 flex-1 items-center gap-4 rounded-md px-2 py-3 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-base text-slate-900">{n.title}</p>
                        <p className="text-sm text-slate-600">
                          {notebookRecord(n, t, common)}
                          {/* The test-day forecast, folded in so a notebook is one
                              line on this page rather than a paragraph of its own. */}
                          {f && f.studied > 0 && (
                            <span className="block text-slate-700 sm:inline">
                              <span className="hidden sm:inline">{' · '}</span>
                              {forecastPhrase(f, t)}
                            </span>
                          )}
                        </p>
                      </div>
                      {n.accuracy == null ? (
                        <span className="shrink-0 text-sm text-slate-500">{common('notStudied')}</span>
                      ) : (
                        <span className="flex shrink-0 items-center gap-3">
                          {/* On a phone the word alone carries it; the bar would squeeze
                              the notebook's name into a sliver. */}
                          <span className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-slate-100 sm:block" aria-hidden>
                            <span
                              className={cn('block h-full rounded-full', masteryBarClass(masteryLevel(n.accuracy)))}
                              style={{ width: `${Math.max(4, Math.min(100, n.accuracy))}%` }}
                            />
                          </span>
                          <span className="text-right text-sm text-slate-900 sm:w-28 sm:text-base">{common(MASTERY_LABEL[masteryLevel(n.accuracy)])}</span>
                        </span>
                      )}
                      <ArrowRight className="size-4 shrink-0 text-slate-400" aria-hidden />
                    </Link>
                    {/* Every row keeps the button's slot once any row has one, so
                        the mastery bars stay in one column. */}
                    {anyReview && (
                      <div className={cn('flex shrink-0 pb-3 sm:w-24 sm:justify-end sm:pb-0', !worthReviewing(f) && 'hidden sm:flex')}>
                        {worthReviewing(f) && (
                          <Button asChild variant="outline" size="sm">
                            <Link
                              href={`/dashboard/flashcards?cards=${f.suggestion.card_ids.join(',')}`}
                              title={t('forecastIfReviewed', {
                                cards: common('cards', { count: f.suggestion.card_ids.length }),
                                after: Math.round(f.suggestion.at_exam),
                              })}
                            >
                              {t('forecastReview', { count: f.suggestion.card_ids.length })}
                            </Link>
                          </Button>
                        )}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
