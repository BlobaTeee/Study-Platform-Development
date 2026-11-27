'use client'

import { useState } from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { scoreOutOfTen } from '@/lib/study-format'
import { cn } from '@/lib/utils'
import { dayLines, studied, summaryParts, type ActivityDay, type ActivitySummary } from '@/lib/activity'

export type { ActivityDay, ActivitySummary }

/** The last fourteen days as a calendar: one square per day, filled when the
 *  student studied, laid out in weeks under weekday names like a printed
 *  calendar. It replaced a bar chart whose heights, mock-test dots and
 *  weekend bands each had to be decoded; a filled square needs no legend
 *  beyond "studied". How much was done is said in words — in the sentence
 *  above and in the lines beside the day that is selected. Every kind of
 *  study counts: cards, quizzes, practice problems, mock tests,
 *  explanations and live rounds. */
export function ActivityStrip({ days, summary }: { days: ActivityDay[]; summary: ActivitySummary }) {
  const t = useTranslations('analytics')
  const locale = useLocale()
  const lastStudied = findLastIndex(days, studied)
  const [selected, setSelected] = useState<number>(lastStudied >= 0 ? lastStudied : days.length - 1)

  const studiedDays = summary.days ?? days.filter(studied).length
  const parts = summaryParts(summary).map((p) => t(p.key, p.values)).join(' · ')
  const weeks = asWeeks(days)
  const weekdayNames = weekdayHeaders(locale)
  const chosen = days[selected]

  return (
    <section aria-labelledby="study-calendar-title">
      <h2 id="study-calendar-title" className="text-base font-semibold text-slate-900">
        {t('last14')}
      </h2>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">
        {studiedDays === 0 || !parts
          ? t('stripEmpty')
          : t('studySummary', { days: studiedDays, parts })}
      </p>

      <div className="mt-4 grid gap-6 md:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] md:items-start">
      <div>
        <div className="grid grid-cols-7 gap-1.5" aria-hidden>
          {weekdayNames.map((name, i) => (
            <span key={i} className="text-center text-xs font-medium text-slate-500">{name}</span>
          ))}
        </div>
        <div className="mt-1.5 space-y-1.5">
          {weeks.map((week, w) => (
            <div key={w} className="grid grid-cols-7 gap-1.5">
              {week.map((cell, c) => {
                if ('outside' in cell) {
                  return (
                    <span key={c} aria-hidden className="grid aspect-square place-items-center text-sm tabular-nums text-slate-300">
                      {cell.outside.getDate() === 1 ? `1/${cell.outside.getMonth() + 1}` : cell.outside.getDate()}
                    </span>
                  )
                }
                const index = cell.index
                const day = days[index]
                const done = studied(day)
                const isToday = index === days.length - 1
                return (
                  <button
                    key={day.date}
                    type="button"
                    onClick={() => setSelected(index)}
                    aria-pressed={selected === index}
                    aria-label={dayDetail(day, t, locale)}
                    className={cn(
                      'aspect-square rounded-md text-sm font-medium tabular-nums transition-[box-shadow,background-color] duration-150',
                      'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode-analytics/40',
                      done
                        ? 'bg-mode-analytics-ink text-white hover:bg-mode-analytics-hover'
                        : 'border border-slate-200 bg-white text-slate-600 hover:border-slate-300',
                      isToday && 'ring-2 ring-slate-900 ring-offset-1',
                    )}
                  >
                    {dateNumber(day.date, index === 0)}
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

      <div className="space-y-2">
        <p className="text-sm text-slate-600">{t('tapDayHint')}</p>
        {chosen && <DayCard day={chosen} t={t} locale={locale} />}
      </div>
      </div>
    </section>
  )
}

type T = (key: string, values?: Record<string, string | number>) => string

/** The selected day: its name, then one line per thing done. */
function DayCard({ day, t, locale }: { day: ActivityDay; t: T; locale: string }) {
  const lines = dayText(day, t, locale)
  return (
    <div className="rounded-lg bg-slate-50 px-4 py-3" aria-live="polite">
      <p className="text-base font-medium text-slate-900">{longDay(day.date, locale)}</p>
      {lines.length === 0 ? (
        <p className="mt-1 text-base text-slate-600">{t('dayRest')}</p>
      ) : (
        <ul className="mt-1.5 space-y-1 text-base leading-relaxed text-slate-800">
          {lines.map((line, i) => (
            <li key={i} className="flex gap-2">
              <span aria-hidden className="mt-[0.6em] size-1.5 shrink-0 rounded-full bg-mode-analytics-ink" />
              {line}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** What was done that day, in words; scores are said out of ten. */
function dayText(day: ActivityDay, t: T, locale: string): string[] {
  return dayLines(day).map(({ key, values }) =>
    'score' in values ? t(key, { score: scoreOutOfTen(values.score, locale) }) : t(key, values))
}

/** The whole day in one sentence, for a screen reader on the square. */
function dayDetail(day: ActivityDay, t: T, locale: string): string {
  const lines = dayText(day, t, locale)
  return `${longDay(day.date, locale)}: ${lines.length ? lines.join('; ') : t('dayRest')}`
}

/** The days laid out Monday-first in weeks, with blanks before the first day
 *  and after the last so each column is always the same weekday. */
function asWeeks(days: ActivityDay[]): Cell[][] {
  if (days.length === 0) return []
  const first = asLocalDate(days[0].date)
  const lead = (first.getDay() + 6) % 7   // Monday = 0
  const cells: Cell[] = []
  for (let i = lead; i > 0; i--) cells.push({ outside: shiftDays(first, -i) })
  days.forEach((_, i) => cells.push({ index: i }))
  const last = asLocalDate(days[days.length - 1].date)
  for (let i = 1; cells.length % 7; i++) cells.push({ outside: shiftDays(last, i) })
  const weeks: Cell[][] = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))
  return weeks
}

/** A square in the calendar: one of the fourteen days, or a day just outside
 *  them that only completes the week, the way a printed month shows the
 *  neighbouring month's dates in grey. */
type Cell = { index: number } | { outside: Date }

function shiftDays(d: Date, n: number): Date {
  return new Date(d.getTime() + n * 86_400_000)
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
