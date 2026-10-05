'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/page-header'
import { analyticsAPI, flashcardsAPI, notebooksAPI, reviewsAPI, streaksAPI } from '@/lib/api'
import { type Due, caughtUpMessage, examGroups } from '@/lib/study-format'
import { cn } from '@/lib/utils'
import { useLocale, useTranslations } from 'next-intl'
import { ArrowRight, ChevronRight } from 'lucide-react'

type Notebook = { id: number; title: string; source_count?: number }
type WeakNotebook = { notebook_id: number; title: string; accuracy: number | null }
type DueCard = { id: number; question: string; status?: string; overdue_days?: number }

/** Today's date as the page title ("Thứ Hai, 5 tháng 10"): it says which
 *  day the owed cards are for, where a time-of-day greeting said nothing. */
function todayTitle(locale: string, d = new Date()): string {
  const text = new Intl.DateTimeFormat(locale, { weekday: 'long', day: 'numeric', month: 'long' }).format(d)
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** The desk for today: what is owed, on an actual card; the week in three
 *  figures; the notebooks with how well each is going. One sheet, no tiles. */
export default function HomePage() {
  const t = useTranslations('home')
  const common = useTranslations('common')
  const locale = useLocale()
  const { data: recsRes, isLoading: recsLoading } = useSWR(['/analytics/recommendations'], () =>
    analyticsAPI.getRecommendations()
  )
  const { data: weekRes } = useSWR(['/study/weekly-stats'], () => reviewsAPI.getWeeklyStats())
  const { data: streakRes } = useSWR(['/study/streak'], () => streaksAPI.getMe())
  // Same keys as the notebooks and flashcards pages: one fetch, shared cache.
  const { data: notebooksRes, isLoading: notebooksLoading } = useSWR(['/notebooks/'], () =>
    notebooksAPI.getNotebooks()
  )
  const { data: dueRes } = useSWR(['/flashcards/due'], () => flashcardsAPI.getDueCards())

  const due: Due = recsRes?.data?.due ?? { due: 0, overdue: 0, new: 0, next_date: null, next_count: 0 }
  // Today's share, not the whole debt: two weeks away should read "40 for
  // today", not a number that makes starting feel pointless.
  const ready = due.today ?? due.due + due.new
  const exams = due.exams_first ?? []
  const dueCards: DueCard[] = dueRes?.data?.results ?? dueRes?.data ?? []
  const firstDue = dueCards[0]
  const weak: WeakNotebook[] = recsRes?.data?.weak_notebooks ?? []
  const accuracyOf = new Map(weak.map((w) => [w.notebook_id, w.accuracy]))
  const reviewsThisWeek: number = weekRes?.data?.reviews_this_week ?? 0
  const accuracyThisWeek: number | null = weekRes?.data?.accuracy_this_week_percent ?? null
  const streak: number = streakRes?.data?.current_streak ?? 0
  const bestStreak: number = streakRes?.data?.best_streak ?? 0
  const notebooks: Notebook[] = (notebooksRes?.data?.results ?? notebooksRes?.data ?? []).slice(0, 6)

  if (recsLoading || notebooksLoading) {
    return <HomeSkeleton />
  }

  if (notebooks.length === 0) {
    return (
      <div className="space-y-8">
        <PageHeader title={todayTitle(locale)} />
        <div data-mode="library" className="sheet flex flex-col items-start gap-5 p-8 md:p-10">
          <p className="max-w-[40ch] text-lg leading-relaxed text-slate-700">{t('firstNotebook')}</p>
          <Button asChild size="lg">
            <Link href="/dashboard/notebooks">{t('newNotebook')}</Link>
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title={todayTitle(locale)}
        lead={
          streak > 0
            ? t('streak', { count: streak }) + (bestStreak > streak ? t('bestStreak', { count: bestStreak }) : '')
            : t('startStreak')
        }
      />

      <div className="sheet grid md:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        {/* What is owed today, as the card it is. */}
        <section data-mode="flashcards" className="border-b border-slate-200 p-6 md:border-b-0 md:border-r md:p-8">
          {ready === 0 ? (
            <div className="flex h-full flex-col justify-center gap-4 py-6">
              <p className="text-lg text-slate-700">{caughtUpMessage(due, common, locale)}</p>
            </div>
          ) : (
            <div className="flex h-full flex-col gap-6">
              <div className="flex items-baseline justify-between gap-4">
                <h2 className="text-lg font-semibold text-slate-900">{t('cardsDueToday', { count: ready })}</h2>
                {/* With debt pushed to coming days, the full overdue count is the
                    very number this page avoids leading with; the line below
                    says what waits, calmly. */}
                {due.overdue > 0 && !due.later && (
                  <span className="text-sm text-red-700">{common('overdueCount', { count: due.overdue })}</span>
                )}
              </div>
              {(exams.length > 0 || due.later || due.new_paused) && (
                // One fact per line: run together with separators, four of them
                // wrapped into a paragraph nobody could scan.
                <ul className="-mt-3 space-y-1 text-sm text-slate-600">
                  {/* Why the order changed comes first: it is the one line here
                      that tells the learner something they chose. */}
                  {examGroups(exams, locale).map((g) => (
                    <li key={g.days} className="text-slate-700">
                      {t('examFirst', { title: g.titles, days: g.days })}
                    </li>
                  ))}
                  {due.later ? <li>{t('laterCount', { count: due.later })}</li> : null}
                  {/* With tests in play, their new cards still come; say that
                      only the other subjects' are waiting. */}
                  {due.new_paused ? <li>{t(exams.length > 0 ? 'newPausedOthers' : 'newPaused')}</li> : null}
                </ul>
              )}

              {/* The first card of the queue, on the stack it sits in. */}
              <Link
                href="/dashboard/flashcards?due=1"
                className="card-stack group relative block rounded-2xl border border-slate-200 bg-white p-6 shadow-sheet transition-shadow duration-200 hover:shadow-lift focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 md:p-8"
              >
                <span className="absolute left-6 -top-px h-[3px] w-12 rounded-b-full bg-mode md:left-8" aria-hidden />
                <span className="font-mono text-xs text-slate-500 tabular-nums">1 / {ready}</span>
                <p className="mt-3 text-xl leading-snug text-slate-900 md:text-2xl text-pretty">
                  {firstDue?.question ?? t('cardsDueToday', { count: ready })}
                </p>
                <span className="mt-6 block h-px w-full bg-slate-100" aria-hidden />
              </Link>

              <div className="mt-auto">
                <Button asChild size="lg">
                  <Link href="/dashboard/flashcards?due=1">
                    {t('studyNow')}
                    <ArrowRight aria-hidden />
                  </Link>
                </Button>
              </div>
            </div>
          )}
        </section>

        {/* The week, and the notebooks. */}
        <div className="flex flex-col">
          <section className="border-b border-slate-200 p-6 md:p-8">
            <h2 className="text-sm font-semibold text-slate-900">{t('thisWeek')}</h2>
            <dl className="mt-3 divide-y divide-slate-100">
              <Figure label={t('reviewsLabel')} value={reviewsThisWeek} />
              {accuracyThisWeek != null && (
                <Figure label={t('recalledLabel')} value={`${accuracyThisWeek}%`} />
              )}
              <Figure label={t('streakLabel')} value={streak} muted={streak === 0} />
            </dl>
          </section>

          <section data-mode="library" className="p-6 md:p-8">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="text-sm font-semibold text-slate-900">{t('jumpBackIn')}</h2>
              <Link href="/dashboard/notebooks" className="text-sm font-medium text-mode-ink hover:underline">
                {t('allNotebooks')}
              </Link>
            </div>
            <ul className="mt-2 divide-y divide-slate-100">
              {notebooks.map((n) => {
                const acc = accuracyOf.get(n.id)
                return (
                  <li key={n.id}>
                    <Link
                      href={`/dashboard/notebooks/${n.id}`}
                      className="group flex items-center gap-3 py-2.5 text-slate-800 hover:text-mode-ink"
                    >
                      <span className="min-w-0 flex-1 truncate">{n.title}</span>
                      {acc != null && (
                        <Mastery pct={acc} />
                      )}
                      <ChevronRight className="size-4 shrink-0 text-slate-400 group-hover:text-mode" aria-hidden />
                    </Link>
                  </li>
                )
              })}
            </ul>
          </section>
        </div>
      </div>
    </div>
  )
}

function Figure({ label, value, muted }: { label: string; value: number | string; muted?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2">
      <dt className="text-sm text-slate-600">{label}</dt>
      <dd className={cn('font-mono text-lg tabular-nums', muted ? 'text-slate-400' : 'text-slate-900')}>{value}</dd>
    </div>
  )
}

/** A short bar and its number: how well a notebook's material is going.
 *  Colour follows the value (analytics green when it is high) and is never
 *  the only signal: the figure sits beside it. */
function Mastery({ pct }: { pct: number }) {
  return (
    <span className="flex shrink-0 items-center gap-2" title={`${pct}%`}>
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <span
          className={cn('block h-full rounded-full', pct >= 70 ? 'bg-mode-analytics' : pct >= 40 ? 'bg-mode-flashcards' : 'bg-red-400')}
          style={{ width: `${Math.max(4, Math.min(100, pct))}%` }}
        />
      </span>
      <span className="w-10 text-right font-mono text-xs text-slate-600 tabular-nums">{pct}%</span>
    </span>
  )
}

/** The page's shape while it loads, so nothing jumps into place. */
function HomeSkeleton() {
  return (
    <div className="space-y-8" aria-busy>
      <div className="mode-rule pt-5">
        <div className="h-8 w-56 rounded bg-slate-100" />
        <div className="mt-3 h-4 w-40 rounded bg-slate-100" />
      </div>
      <div className="sheet grid md:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="space-y-6 p-8">
          <div className="h-5 w-40 rounded bg-slate-100" />
          <div className="h-40 rounded-2xl bg-slate-100" />
          <div className="h-11 w-36 rounded-lg bg-slate-100" />
        </div>
        <div className="space-y-3 p-8">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="h-5 rounded bg-slate-100" />
          ))}
        </div>
      </div>
    </div>
  )
}
