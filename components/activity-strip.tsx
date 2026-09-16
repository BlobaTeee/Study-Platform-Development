'use client'

import { useId, useState } from 'react'
import { cn } from '@/lib/utils'

export type ActivityDay = {
  date: string // ISO date, the student's own day
  reviews: number
  correct: number
  accuracy: number | null
  mock_scores: number[]
}

export type ActivitySummary = {
  reviews: number
  accuracy: number | null
  mock_tests: number
}

/** The last fourteen days of study as one strip: a column per day, its
 *  height the number of cards graded, a mark above it on days a mock test
 *  was sat. Accuracy is not drawn — a second measure on the same mark reads
 *  wrong — it lives in the hover readout and the line under the strip.
 *
 *  One series, so no legend for the bars; the mock-test mark is the one thing
 *  that needs naming. A skipped day is a gap, on purpose. */
export function ActivityStrip({ days, summary }: { days: ActivityDay[]; summary: ActivitySummary }) {
  const [active, setActive] = useState<number | null>(null)
  const tableId = useId()
  const max = Math.max(1, ...days.map((d) => d.reviews))
  const empty = summary.reviews === 0 && summary.mock_tests === 0
  const activeDay = active == null ? null : days[active]

  return (
    <section aria-labelledby={`${tableId}-title`}>
      <div className="mb-1 flex items-center justify-between gap-3">
        <h2 id={`${tableId}-title`} className="text-xl font-semibold text-slate-900">
          Last 14 days
        </h2>
        <p className="flex items-center gap-1.5 text-sm text-slate-500">
          <span aria-hidden className="inline-block size-2 rounded-full bg-mode-quizzes ring-2 ring-white" />
          Mock test
        </p>
      </div>
      <p className="mb-5 text-sm text-slate-500">
        {empty
          ? 'Nothing yet — grade some cards and the days fill in here.'
          : summaryLine(summary)}
      </p>

      {/* The plot. Each column is the hit target for its day, taller than the
          bar it holds, so a two-card day is as easy to hover as a thirty-card
          one. The readout is one element repositioned, not one per column. */}
      <div className="relative">
        {activeDay && active != null && (
          <div
            role="status"
            className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm shadow-sheet"
            style={{ left: `${((active + 0.5) / days.length) * 100}%` }}
          >
            <span className="font-mono font-semibold tabular-nums text-slate-900">
              {activeDay.reviews} card{activeDay.reviews === 1 ? '' : 's'}
            </span>
            <span className="text-slate-500"> · {weekdayLong(activeDay.date)}</span>
            {activeDay.accuracy != null && (
              <span className="text-slate-500"> · {activeDay.accuracy}% recalled</span>
            )}
            {activeDay.mock_scores.map((s, i) => (
              <span key={i} className="text-slate-500"> · mock test {Math.round(s)}%</span>
            ))}
          </div>
        )}

        <div
          className="flex h-28 items-end gap-0.5 border-b border-slate-200"
          onMouseLeave={() => setActive(null)}
          aria-describedby={tableId}
        >
          {days.map((day, i) => {
            const studied = day.reviews > 0
            const height = studied ? Math.max(4, Math.round((day.reviews / max) * 100)) : 0
            return (
              <button
                key={day.date}
                type="button"
                className="group relative flex h-full min-w-0 flex-1 items-end justify-center rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mode-analytics"
                onMouseEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                aria-label={dayLabel(day)}
              >
                {day.mock_scores.length > 0 && (
                  <span
                    aria-hidden
                    className="absolute left-1/2 size-2 -translate-x-1/2 rounded-full bg-mode-quizzes ring-2 ring-white"
                    style={{ bottom: `calc(${height}% + 6px)` }}
                  />
                )}
                <span
                  aria-hidden
                  className={cn(
                    'block w-[70%] max-w-6 rounded-t bg-mode-analytics-hover transition-opacity',
                    active != null && active !== i && 'opacity-40'
                  )}
                  style={{ height: `${height}%` }}
                />
              </button>
            )
          })}
        </div>
        <div className="mt-1.5 flex gap-0.5" aria-hidden>
          {days.map((day, i) => (
            <span
              key={day.date}
              className={cn(
                'flex-1 text-center font-mono text-[11px] uppercase text-slate-400',
                i === days.length - 1 && 'text-slate-600'
              )}
            >
              {i === days.length - 1 ? 'now' : weekdayInitial(day.date)}
            </span>
          ))}
        </div>
      </div>

      {/* The same data as a table, for screen readers and for anyone the
          columns don't serve. */}
      <table id={tableId} className="sr-only">
        <caption>Cards graded per day, last 14 days</caption>
        <thead>
          <tr><th>Day</th><th>Cards</th><th>Recalled</th><th>Mock tests</th></tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.date}>
              <td>{weekdayLong(day.date)}</td>
              <td>{day.reviews}</td>
              <td>{day.accuracy == null ? '—' : `${day.accuracy}%`}</td>
              <td>{day.mock_scores.length ? day.mock_scores.map((s) => `${Math.round(s)}%`).join(', ') : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function summaryLine(s: ActivitySummary): string {
  const parts = [`${s.reviews} card${s.reviews === 1 ? '' : 's'} graded`]
  if (s.accuracy != null) parts.push(`${s.accuracy}% recalled`)
  if (s.mock_tests) parts.push(`${s.mock_tests} mock test${s.mock_tests === 1 ? '' : 's'}`)
  return parts.join(' · ')
}

function dayLabel(day: ActivityDay): string {
  const bits = [weekdayLong(day.date), `${day.reviews} card${day.reviews === 1 ? '' : 's'}`]
  if (day.accuracy != null) bits.push(`${day.accuracy}% recalled`)
  if (day.mock_scores.length) bits.push(`${day.mock_scores.length} mock test${day.mock_scores.length === 1 ? '' : 's'}`)
  return bits.join(', ')
}

// Dates arrive as bare ISO days in the student's zone; parsing them as local
// noon keeps the weekday right on either side of midnight.
function asLocalDate(iso: string): Date {
  return new Date(`${iso}T12:00:00`)
}

function weekdayInitial(iso: string): string {
  return asLocalDate(iso).toLocaleDateString(undefined, { weekday: 'narrow' })
}

function weekdayLong(iso: string): string {
  return asLocalDate(iso).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
}
