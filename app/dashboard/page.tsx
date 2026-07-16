'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { analyticsAPI, notebooksAPI, reviewsAPI, streaksAPI } from '@/lib/api'
import { type Due, dueBreakdown, caughtUpMessage } from '@/lib/study-format'
import { cn } from '@/lib/utils'
import { ArrowRight, Flame, NotebookText, Target, Zap } from 'lucide-react'

type Notebook = { id: number; title: string }
type WeakSource = { source_id: number; title: string; accuracy: number | null }

function greeting(d = new Date()): string {
  const h = d.getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

export default function HomePage() {
  const { data: recsRes, isLoading: recsLoading } = useSWR(['/analytics/recommendations'], () =>
    analyticsAPI.getRecommendations()
  )
  const { data: weekRes } = useSWR(['/study/weekly-stats'], () => reviewsAPI.getWeeklyStats())
  const { data: streakRes } = useSWR(['/study/streak'], () => streaksAPI.getMe())
  // Same key as the notebooks list page so SWR serves one fetch and a
  // create/delete there refreshes this list too.
  const { data: notebooksRes, isLoading: notebooksLoading } = useSWR(['/notebooks/'], () =>
    notebooksAPI.getNotebooks()
  )

  const due: Due = recsRes?.data?.due ?? {
    due: 0,
    overdue: 0,
    new: 0,
    next_date: null,
    next_count: 0,
  }
  const ready = due.due + due.new
  const weakSources: WeakSource[] = (recsRes?.data?.weak_sources ?? []).slice(0, 3)
  const reviewsThisWeek: number = weekRes?.data?.reviews_this_week ?? 0
  const accuracyThisWeek: number | null = weekRes?.data?.accuracy_this_week_percent ?? null
  const streak: number = streakRes?.data?.current_streak ?? 0
  const bestStreak: number = streakRes?.data?.best_streak ?? 0
  const notebooks: Notebook[] = (
    notebooksRes?.data?.results ??
    notebooksRes?.data ??
    []
  ).slice(0, 4)

  const hasAnything = notebooks.length > 0

  if (recsLoading || notebooksLoading) {
    return <p className="text-xl text-slate-500 text-center py-20">Loading…</p>
  }

  return (
    <div className="max-w-5xl space-y-8">
      {/* Greeting + streak */}
      <div className="rise flex flex-wrap items-end justify-between gap-4 border-t-[3px] border-mode-library pt-4">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-library">
            Today
          </p>
          <h1 className="mt-1 font-display text-3xl font-semibold text-slate-900 md:text-4xl">
            {greeting()}
          </h1>
        </div>
        {streak > 0 ? (
          <div className="flex items-center gap-2 rounded-full bg-amber-50 px-4 py-2 text-amber-900">
            <Flame className="size-5 text-amber-500" />
            <span className="font-mono text-sm tabular-nums">
              {streak} day streak{bestStreak > streak ? ` · best ${bestStreak}` : ''}
            </span>
          </div>
        ) : (
          <p className="font-mono text-sm text-slate-500">Study today to start a streak.</p>
        )}
      </div>

      {!hasAnything ? (
        <Card className="rise flex flex-col items-center gap-4 border-slate-200 p-12 text-center shadow-sheet">
          <NotebookText className="size-14 text-slate-300" />
          <p className="text-xl text-slate-600">Create your first notebook to start studying.</p>
          <Button
            asChild
            size="lg"
            className="h-12 bg-mode-library text-lg text-white hover:bg-mode-library-hover"
          >
            <Link href="/dashboard/notebooks">New notebook</Link>
          </Button>
        </Card>
      ) : (
        <>
          {/* Due today (primary) + this week */}
          <div className="grid gap-6 md:grid-cols-3">
            <Card
              className="rise border-slate-200 p-6 shadow-sheet md:col-span-2"
              style={{ animationDelay: '60ms' }}
            >
              {ready === 0 ? (
                <div className="flex items-center gap-3 py-2">
                  <Target className="size-5 shrink-0 text-mode-analytics" />
                  <p className="text-lg text-slate-700">{caughtUpMessage(due)}</p>
                </div>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-5">
                  <div className="flex min-w-0 items-baseline gap-4">
                    <span className="font-mono text-5xl font-semibold tabular-nums text-slate-900">
                      {ready}
                    </span>
                    <div className="min-w-0">
                      <p className="text-lg text-slate-900">
                        card{ready === 1 ? '' : 's'} due today
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
                    className="h-12 shrink-0 bg-mode-flashcards px-8 text-lg text-white hover:bg-mode-flashcards-hover"
                  >
                    <Link href="/dashboard/flashcards?due=1">
                      Study now
                      <ArrowRight className="ml-2 size-5" />
                    </Link>
                  </Button>
                </div>
              )}
            </Card>

            <Card
              className="rise border-slate-200 p-6 shadow-sheet"
              style={{ animationDelay: '120ms' }}
            >
              <div className="mb-3 flex items-center gap-2 text-slate-500">
                <Zap className="size-4 text-mode-flashcards" />
                <span className="text-sm">This week</span>
              </div>
              <p className="font-mono text-3xl font-semibold tabular-nums text-slate-900">
                {reviewsThisWeek}
              </p>
              <p className="text-sm text-slate-500">
                review{reviewsThisWeek === 1 ? '' : 's'}
                {accuracyThisWeek != null ? ` · ${accuracyThisWeek}% recalled` : ''}
              </p>
            </Card>
          </div>

          {/* Jump back in + weakest right now */}
          <div className="grid gap-6 md:grid-cols-2">
            <Card
              className="rise border-slate-200 p-6 shadow-sheet"
              style={{ animationDelay: '180ms' }}
            >
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <NotebookText className="size-5 text-mode-library" />
                  <h2 className="text-xl font-semibold text-slate-900">Jump back in</h2>
                </div>
                <Link
                  href="/dashboard/notebooks"
                  className="shrink-0 text-sm font-medium text-mode-library hover:underline"
                >
                  All notebooks →
                </Link>
              </div>
              <ul className="divide-y divide-slate-100">
                {notebooks.map((n) => (
                  <li key={n.id}>
                    <Link
                      href={`/dashboard/notebooks/${n.id}`}
                      className="flex items-center gap-3 py-3 text-slate-800 hover:text-mode-library"
                    >
                      <NotebookText className="size-4 shrink-0 text-slate-400" />
                      <span className="truncate">{n.title}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>

            <Card
              className="rise border-slate-200 p-6 shadow-sheet"
              style={{ animationDelay: '240ms' }}
            >
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Target className="size-5 text-mode-analytics" />
                  <h2 className="text-xl font-semibold text-slate-900">Weakest right now</h2>
                </div>
                <Link
                  href="/dashboard/analytics"
                  className="shrink-0 text-sm font-medium text-mode-analytics hover:underline"
                >
                  Analytics →
                </Link>
              </div>
              {weakSources.length === 0 ? (
                <p className="py-3 text-slate-500">
                  Study a document and its recall shows up here.
                </p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {weakSources.map((s) => (
                    <li key={s.source_id} className="flex items-center gap-4 py-3">
                      <span className="min-w-0 flex-1 truncate text-slate-800">{s.title}</span>
                      <span className="shrink-0 font-mono text-sm tabular-nums text-slate-600">
                        {s.accuracy == null ? 'Not studied' : `${s.accuracy}%`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
