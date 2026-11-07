'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { ForgottenNotebook } from '@/lib/api'
import { cn } from '@/lib/utils'
import { shownAs } from '@/lib/translate'
import { InPageLanguage, useInPageLanguage } from '@/components/in-page-language'

/** Cards last answered wrong: one short line per notebook, most forgotten
 *  first, opening onto that notebook's concept groups. Listed flat, every
 *  notebook's groups piled into one long list with subjects mixed together.
 *  Closed by default; the line's own button relearns the whole notebook. */
export function ForgottenCards({ notebooks }: { notebooks: ForgottenNotebook[] }) {
  const t = useTranslations('analytics')
  const common = useTranslations('common')
  const [open, setOpen] = useState<Set<number | null>>(new Set())
  // Concept names and sample questions are in their documents' language.
  const found = useInPageLanguage(notebooks.flatMap((nb) => nb.groups.flatMap((g) => [g.label, g.sample])))

  const toggle = (id: number | null) =>
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <ul className="mt-3 divide-y divide-slate-200 rounded-xl border border-slate-200">
      {notebooks.map((nb) => {
        const isOpen = open.has(nb.notebook_id)
        const panelId = `forgotten-${nb.notebook_id ?? 'none'}`
        return (
          <li key={nb.notebook_id ?? 'none'}>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 p-3 sm:p-4">
              <button
                type="button"
                onClick={() => toggle(nb.notebook_id)}
                aria-expanded={isOpen}
                aria-controls={panelId}
                className="-m-1 flex min-w-0 flex-1 basis-56 items-center gap-2 rounded-md p-1 text-left focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
              >
                <ChevronDown
                  className={cn(
                    'size-4 shrink-0 text-slate-500 transition-transform duration-200 motion-reduce:transition-none',
                    !isOpen && '-rotate-90'
                  )}
                  aria-hidden
                />
                <span className="min-w-0">
                  <span className="block truncate text-base font-medium text-slate-900">
                    {nb.title || t('untitledNotebook')}
                  </span>
                  <span className="block text-sm text-slate-600">
                    {t('forgottenNotebookMeta', {
                      cards: common('cards', { count: nb.count }),
                      groups: nb.groups.length,
                    })}
                  </span>
                </span>
              </button>
              <Button asChild variant="outline" size="sm" className="shrink-0">
                <Link href={`/dashboard/flashcards?cards=${nb.card_ids.join(',')}`}>
                  {t('relearnNotebook', { count: nb.count })}
                </Link>
              </Button>
            </div>

            {isOpen && (
              <ul id={panelId} className="divide-y divide-slate-100 border-t border-slate-100 bg-slate-50/60 px-2.5 sm:px-4">
                {nb.groups.map((g) => (
                  <li key={g.key} className="flex flex-col items-start gap-2 py-3 sm:flex-row sm:items-center sm:gap-4 sm:pl-6">
                    <div className="min-w-0 w-full flex-1">
                      <p className="text-base text-slate-900">
                        <InPageLanguage text={g.label} found={found} />
                        <span className="ml-2 text-sm text-slate-600">{common('cards', { count: g.count })}</span>
                      </p>
                      <p className="line-clamp-2 text-sm text-slate-600 sm:line-clamp-1">
                        {t('forgottenSample', { question: shownAs(found, g.sample) ?? g.sample })}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-1 sm:gap-2">
                      <Button asChild variant="outline" size="sm">
                        <Link href={`/dashboard/flashcards?cards=${g.card_ids.join(',')}`}>{t('relearnGroup')}</Link>
                      </Button>
                      <Button asChild variant="ghost" size="sm" className="px-2 sm:px-3">
                        <Link href={`/dashboard/explain?cards=${g.card_ids.join(',')}&concept=${encodeURIComponent(g.label)}`}>
                          {t('explainGroup')}
                        </Link>
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </li>
        )
      })}
    </ul>
  )
}
