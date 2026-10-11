'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronDown } from 'lucide-react'
import type { KeyPoint } from '@/lib/api'
import { cn } from '@/lib/utils'

/** A document's main ideas, the ones a student must know first. Each opens
 *  onto the passage it was read from, so the list can be checked against the
 *  document rather than taken on trust. Cards and questions are written from
 *  these same ideas. */
export function KeyPoints({ points }: { points: KeyPoint[] }) {
  const t = useTranslations('notebooks')
  const [open, setOpen] = useState<number | null>(null)
  const core = points.filter((p) => p.importance === 'core').length

  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900">{t('keyPoints')}</h3>
      <p className="mt-1 text-sm text-slate-600">{t('keyPointsLead', { core, total: points.length })}</p>
      <ol className="mt-3 space-y-1">
        {points.map((p, i) => {
          const isOpen = open === i
          return (
            <li key={i}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : i)}
                aria-expanded={isOpen}
                className="group -mx-2 flex w-full items-start gap-3 rounded-md px-2 py-2 text-left hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
              >
                <span
                  className={cn(
                    'mt-2 size-2 shrink-0 rounded-full',
                    p.importance === 'core' ? 'bg-mode' : 'border border-slate-400 bg-white'
                  )}
                  aria-hidden
                />
                <span className="min-w-0 flex-1">
                  <span className="block max-w-[70ch] text-base leading-relaxed text-slate-900">{p.point}</span>
                  {p.importance !== 'core' && (
                    <span className="block text-xs text-slate-500">{t('supportingIdea')}</span>
                  )}
                </span>
                <ChevronDown
                  className={cn('mt-1.5 size-4 shrink-0 text-slate-400 transition-transform duration-200 motion-reduce:transition-none', isOpen && 'rotate-180')}
                  aria-hidden
                />
                <span className="sr-only">{isOpen ? t('hidePassage') : t('showPassage')}</span>
              </button>
              {isOpen && (
                <blockquote className="mb-2 ml-5 max-w-[70ch] rounded-md bg-slate-50 px-4 py-3 text-sm leading-relaxed text-slate-700">
                  {p.passage}
                </blockquote>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
