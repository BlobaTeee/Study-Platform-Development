'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import useSWR from 'swr'
import { ChevronDown } from 'lucide-react'
import { InPageLanguage, useInPageLanguage } from '@/components/in-page-language'
import { notebooksAPI, type ConceptState, type KeyPoint } from '@/lib/api'
import { keyPointStates } from '@/lib/key-points'
import { cn } from '@/lib/utils'

/** How many ideas show before "show more": the core ones, up to this many. */
const FIRST_SHOWN = 5

// The mastery colours used across the app: emerald strong, amber shaky, red
// weak; an empty ring for not yet studied.
const DOT: Record<ConceptState, string> = {
  strong: 'bg-mode-analytics',
  shaky: 'bg-mode-flashcards',
  weak: 'bg-red-500',
  not_studied: 'border border-slate-400',
}
const WORD: Record<ConceptState, string> = {
  strong: 'text-mode-analytics-ink',
  shaky: 'text-mode-flashcards-ink',
  weak: 'text-red-700',
  not_studied: 'text-slate-600',
}

/** A document's main ideas, as a short list with how well each is known. */
export function KeyPoints({ points, notebookId, sourceId }: {
  points: KeyPoint[]
  notebookId: number
  sourceId: number
}) {
  const t = useTranslations('notebooks')
  const { data } = useSWR(['/map', notebookId], () => notebooksAPI.getMap(notebookId))
  const states = keyPointStates(data?.data.concepts ?? [], sourceId, points.length)

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-slate-900">{t('keyPoints')}</h3>
      <PointList points={points} states={states} />
    </div>
  )
}

/** The list: one line each, the core ones first and the rest behind "show
 *  more", each with how well it is known. The full idea and the passage it
 *  was read from open on a click. */
function PointList({ points, states }: { points: KeyPoint[]; states: (ConceptState | null)[] }) {
  const t = useTranslations('notebooks')
  const [open, setOpen] = useState<number | null>(null)
  const [all, setAll] = useState(false)
  // In the page language; the passage stays in the document's own words.
  const found = useInPageLanguage(points.flatMap((p) => [p.label, p.point]))

  const core = points.filter((p) => p.importance === 'core')
  const first = (core.length ? core : points).slice(0, FIRST_SHOWN)
  const shown = all ? points : first
  const hidden = points.length - first.length

  return (
    <div>
      <ul className="divide-y divide-slate-100">
        {shown.map((p) => {
          const i = points.indexOf(p)
          const isOpen = open === i
          const state = states[i]
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
                  <InPageLanguage text={p.label || p.point} found={found} />
                </span>
                {state && (
                  <span className={cn('flex shrink-0 items-center gap-1.5 text-xs', WORD[state])}>
                    <span className={cn('size-2 rounded-full', DOT[state])} aria-hidden />
                    {t(`state_${state}`)}
                  </span>
                )}
                <ChevronDown
                  className={cn('size-4 shrink-0 text-slate-400 transition-transform duration-200 motion-reduce:transition-none', isOpen && 'rotate-180')}
                  aria-hidden
                />
              </button>
              {isOpen && (
                <div className="mb-2 ml-[1.125rem] max-w-[70ch] space-y-2 text-sm leading-relaxed">
                  {p.label && <p className="text-slate-800"><InPageLanguage text={p.point} found={found} /></p>}
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
