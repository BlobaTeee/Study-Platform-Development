'use client'

import { useState } from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { scoreOutOfTen } from '@/lib/study-format'
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
  correct?: number
  accuracy: number | null
  mock_tests: number
}

/** The last fourteen days as a calendar: one square per day, filled when the
 *  student studied, laid out in weeks under weekday names like a printed
 *  calendar. It replaced a bar chart whose heights, mock-test dots and
 *  weekend bands each had to be decoded; a filled square needs no legend
 *  beyond "studied". How much was done is said in words — in the sentence
 *  above and in the line under the day that is selected. */
export function ActivityStrip({ days, summary }: { days: ActivityDay[]; summary: ActivitySummary }) {
  const t = useTranslations('analytics')
  const locale = useLocale()
  const lastStudied = findLastIndex(days, (d) => d.reviews > 0 || d.mock_scores.length > 0)
  const [selected, setSelected] = useState<number>(lastStudied >= 0 ? lastStudied : days.length - 1)

  const studiedDays = days.filter((d) => d.reviews > 0 || d.mock_scores.length > 0).length
  const recalled = summary.correct ?? days.reduce((n, d) => n + d.correct, 0)
  const weeks = asWeeks(days)
  const weekdayNames = weekdayHeaders(locale)
  const chosen = days[selected]

  return (
    <section aria-labelledby="study-calendar-title">
      <h2 id="study-calendar-title" className="text-base font-semibold text-slate-900">
        {t('last14')}
      </h2>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        {studiedDays === 0
          ? t('stripEmpty')
          : t('studySummary', { days: studiedDays, cards: summary.reviews, recalled })}
        {summary.mock_tests > 0 && ` ${t('mockSummary', { count: summary.mock_tests })}`}
      </p>

      <div className="mt-4 max-w-md">
        <div className="grid grid-cols-7 gap-1.5" aria-hidden>
          {weekdayNames.map((name, i) => (
            <span key={i} className="text-center text-xs font-medium text-slate-500">{name}</span>
          ))}
        </div>
        <div className="mt-1.5 space-y-1.5">
          {weeks.map((week, w) => (
            <div key={w} className="grid grid-cols-7 gap-1.5">
              {week.map((cell, c) => {
                if (cell === null) return <span key={c} aria-hidden />
                const day = days[cell]
                const studied = day.reviews > 0 || day.mock_scores.length > 0
                const isToday = cell === days.length - 1
                return (
                  <button
                    key={day.date}
                    type="button"
                    onClick={() => setSelected(cell)}
                    aria-pressed={selected === cell}
                    aria-label={dayDetail(day, t, locale)}
                    className={cn(
                      'aspect-square rounded-md text-sm font-medium tabular-nums transition-[box-shadow,background-color] duration-150',
                      'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode-analytics/40',
                      studied
                        ? 'bg-mode-analytics-ink text-white hover:bg-mode-analytics-hover'
                        : 'border border-slate-200 bg-white text-slate-600 hover:border-slate-300',
                      isToday && 'ring-2 ring-slate-900 ring-offset-1',
                    )}
                  >
                    {dateNumber(day.date, cell === 0)}
                  </button>
                )
              })}
            </div>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600" aria-hidden>
          <span className="flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-sm bg-mode-analytics-ink" />
            {t('legendStudied')}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-sm border border-slate-300 bg-white" />
            {t('legendRest')}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-sm ring-2 ring-slate-900 ring-offset-1" />
            {t('legendToday')}
          </span>
        </div>
      </div>

      {chosen && (
        <p className="mt-4 rounded-lg bg-slate-50 px-3.5 py-2.5 text-sm text-slate-800" aria-live="polite">
          {dayDetail(chosen, t, locale)}
        </p>
      )}
    </section>
  )
}

type T = (key: string, values?: Record<string, string | number>) => string

/** One day in plain words: what was reviewed, what stuck, any mock test. */
function dayDetail(day: ActivityDay, t: T, locale: string): string {
  const name = longDay(day.date, locale)
  const parts: string[] = []
  if (day.reviews > 0) {
    parts.push(t('dayReviewed', { day: name, cards: day.reviews, recalled: day.correct, forgot: day.reviews - day.correct }))
  }
  for (const s of day.mock_scores) {
    parts.push(t('dayMock', { score: scoreOutOfTen(s, locale) }))
  }
  if (parts.length === 0) return t('dayRest', { day: name })
  // The mock-test sentence needs the day's name only when it stands alone.
  return day.reviews > 0 ? parts.join(' ') : `${t('dayOnly', { day: name })} ${parts.join(' ')}`
}

/** The days laid out Monday-first in weeks, with blanks before the first day
 *  and after the last so each column is always the same weekday. */
function asWeeks(days: ActivityDay[]): (number | null)[][] {
  if (days.length === 0) return []
  const lead = (asLocalDate(days[0].date).getDay() + 6) % 7   // Monday = 0
  const cells: (number | null)[] = [...Array(lead).fill(null), ...days.map((_, i) => i)]
  while (cells.length % 7) cells.push(null)
  const weeks: (number | null)[][] = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))
  return weeks
}

/** Weekday names, Monday first, as short as the language allows while all
 *  seven stay distinct: Vietnamese "T2 … CN", English "Mon … Sun" — the
 *  narrowest English form ("M T W T F S S") repeats letters and reads as
 *  noise, which is exactly what this view is meant to avoid. */
function weekdayHeaders(locale: string): string[] {
  const monday = new Date('2026-09-28T12:00:00')
  const names = (style: 'narrow' | 'short') =>
    [...Array(7)].map((_, i) => new Intl.DateTimeFormat(locale, { weekday: style })
      .format(new Date(monday.getTime() + i * 86_400_000)))
  const narrow = names('narrow')
  return new Set(narrow).size === 7 ? narrow : names('short')
}

// Dates arrive as bare ISO days in the student's zone; parsing them as local
// noon keeps the weekday right on either side of midnight.
function asLocalDate(iso: string): Date {
  return new Date(`${iso}T12:00:00`)
}

/** The day of the month; the first square and any 1st also say the month. */
function dateNumber(iso: string, first: boolean): string {
  const d = asLocalDate(iso)
  return first || d.getDate() === 1 ? `${d.getDate()}/${d.getMonth() + 1}` : String(d.getDate())
}

function longDay(iso: string, locale: string): string {
  const text = asLocalDate(iso).toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function findLastIndex<T>(items: T[], test: (item: T) => boolean): number {
  for (let i = items.length - 1; i >= 0; i--) if (test(items[i])) return i
  return -1
}
