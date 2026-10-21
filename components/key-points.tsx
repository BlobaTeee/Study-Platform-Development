'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronDown } from 'lucide-react'
import type { KeyPoint } from '@/lib/api'
import { cn } from '@/lib/utils'

/** How many ideas show before "show more": the core ones, up to this many. */
const FIRST_SHOWN = 5

/** A document's main ideas as a short list: one line each, the core ones
 *  first and the rest behind "show more". The full idea and the passage it
 *  was read from open on a click. The long form is what cards and questions
 *  are written from; this list only has to say what the document is about. */
export function KeyPoints({ points }: { points: KeyPoint[] }) {
  const t = useTranslations('notebooks')
  const [open, setOpen] = useState<number | null>(null)
  const [all, setAll] = useState(false)

  const core = points.filter((p) => p.importance === 'core')
  const first = (core.length ? core : points).slice(0, FIRST_SHOWN)
  const shown = all ? points : first
  const hidden = points.length - first.length

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-sm font-semibold text-slate-900">{t('keyPoints')}</h3>
        <p className="text-xs text-slate-500">{t('keyPointsLead')}</p>
      </div>
      <ul className="mt-2 divide-y divide-slate-100">
        {shown.map((p) => {
          const i = points.indexOf(p)
          const isOpen = open === i
          return (
            <li key={i}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : i)}
                aria-expanded={isOpen}
                className="flex w-full items-center gap-3 py-2 text-left focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
              >
                <span
                  className={cn(
                    'size-1.5 shrink-0 rounded-full',
                    p.importance === 'core' ? 'bg-mode' : 'border border-slate-400'
                  )}
                  aria-hidden
                />
                <span className={cn('min-w-0 flex-1 text-sm text-slate-900', !isOpen && 'truncate')}>
                  {p.label || p.point}
                </span>
                <ChevronDown
                  className={cn('size-4 shrink-0 text-slate-400 transition-transform duration-200 motion-reduce:transition-none', isOpen && 'rotate-180')}
                  aria-hidden
                />
              </button>
              {isOpen && (
                <div className="mb-2 ml-[1.125rem] max-w-[70ch] space-y-2 text-sm leading-relaxed">
                  {p.label && <p className="text-slate-800">{p.point}</p>}
                  {/* The passage is the document's own words, kept to show the idea is
                      really there; labelled so it does not read as the summary twice. */}
                  <figure className="rounded-md bg-slate-50 px-3 py-2">
                    <figcaption className="text-xs font-medium text-slate-600">{t('quotedFrom')}</figcaption>
                    <blockquote className="mt-1 text-[13px] leading-relaxed text-slate-600">{p.passage}</blockquote>
                  </figure>
                </div>
              )}
            </li>
          )
        })}
      </ul>
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          className="mt-1 text-sm font-medium text-mode-ink underline-offset-4 hover:underline"
        >
          {all ? t('fewerIdeas') : t('moreIdeas', { count: hidden })}
        </button>
      )}
    </div>
  )
}
