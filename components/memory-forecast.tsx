'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import type { NotebookForecast } from '@/lib/api'

/** How many studied cards each notebook will still be remembered on test day,
 *  in counts rather than percentages, and the review that would raise it
 *  most. Counts are expected values from the memory model, so they are
 *  rounded and said as "about". */
export function MemoryForecast({ notebooks }: { notebooks: NotebookForecast[] }) {
  const t = useTranslations('analytics')
  const common = useTranslations('common')

  return (
    <ul className="mt-3 divide-y divide-slate-100">
      {notebooks.map((nb) => {
        const now = Math.round(nb.now)
        const later = Math.round(nb.at_exam)
        const after = Math.round(nb.suggestion.at_exam)
        const toReview = nb.suggestion.card_ids.length
        return (
          <li key={nb.notebook_id} className="flex flex-col items-start gap-3 py-4 sm:flex-row sm:items-center sm:gap-6">
            <div className="min-w-0 flex-1">
              <p className="text-base font-medium text-slate-900">
                {nb.title}
                <span className="ml-2 text-sm font-normal text-slate-600">
                  {nb.has_exam ? t('forecastExamIn', { days: nb.days_ahead }) : t('forecastWeekAhead')}
                </span>
              </p>
              <p className="mt-1 max-w-[65ch] text-sm leading-relaxed text-slate-700">
                {t('forecastNow', { now, studied: nb.studied })}{' '}
                {t(nb.has_exam ? 'forecastLaterExam' : 'forecastLaterWeek', { later })}
                {toReview > 0 && after > later ? ` ${t('forecastIfReviewed', { cards: common('cards', { count: toReview }), after })}` : ''}
              </p>
              {nb.unseen > 0 && <p className="mt-1 text-xs text-slate-500">{t('forecastUnseen', { count: nb.unseen })}</p>}
            </div>
            {toReview > 0 && after > later && (
              <Button asChild variant="outline" size="sm" className="shrink-0">
                <Link href={`/dashboard/flashcards?cards=${nb.suggestion.card_ids.join(',')}`}>
                  {t('forecastReview', { count: toReview })}
                </Link>
              </Button>
            )}
          </li>
        )
      })}
    </ul>
  )
}
