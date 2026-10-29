'use client'

import { Suspense, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { ArrowRight } from 'lucide-react'
import { OwnProblemForm } from '@/components/own-problem-form'
import { PageHeader } from '@/components/page-header'
import { exercisesAPI, type ExerciseSummary } from '@/lib/api'
import { filtered, filtersFor, inPracticeOrder, parseFilter, type PracticeFilter } from '@/lib/practice'
import { cn } from '@/lib/utils'

/** Every practice problem in one place, whatever it came from: written from
 *  a notebook's document, or brought by the student. Where it came from is
 *  a filter, not a second place to look. `?notebook=<id>` or `?notebook=own`
 *  opens it filtered, which is how a notebook links here. */
function PracticeList() {
  const t = useTranslations('practice')
  const router = useRouter()
  const searchParams = useSearchParams()
  const filter = parseFilter(searchParams.get('notebook'))
  const { data, isLoading } = useSWR(['/exercises', 'all'], () => exercisesAPI.list({}))
  const all: ExerciseSummary[] = data?.data?.results ?? []
  const filters = filtersFor(all)
  const shown = inPracticeOrder(filtered(all, filter))
  const [writing, setWriting] = useState(filter === 'own')

  const pick = (next: PracticeFilter) => {
    const query = next === 'all' ? '' : `?notebook=${next}`
    router.replace(`/dashboard/practice${query}`, { scroll: false })
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <PageHeader title={t('title')} />

      <OwnProblemForm open={writing} onToggle={() => setWriting((v) => !v)} />

      <section className="sheet p-6 md:p-8" aria-labelledby="practice-list-title">
        <h2 id="practice-list-title" className="sr-only">{t('title')}</h2>
        <p className="max-w-[65ch] text-sm text-slate-600">{t('pageLead')}</p>

        {filters.length > 1 && (
          <div role="group" aria-label={t('filtersLabel')} className="mt-4 flex flex-wrap gap-2">
            <FilterChip active={filter === 'all'} onClick={() => pick('all')} label={t('filterAll')} count={all.length} />
            {filters.map((f) => (
              <FilterChip
                key={f.key}
                active={filter === f.key}
                onClick={() => pick(f.key)}
                label={f.key === 'own' ? t('filterOwn') : f.title}
                count={f.count}
              />
            ))}
          </div>
        )}

        {isLoading ? (
          <div className="mt-4 h-24 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none" aria-busy />
        ) : shown.length === 0 ? (
          <p className="mt-4 max-w-[65ch] text-slate-600">{all.length === 0 ? t('listEmpty') : t('listEmptyFiltered')}</p>
        ) : (
          <ul className="mt-4 divide-y divide-slate-100 border-t border-slate-100">
            {shown.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/dashboard/practice/${p.id}`}
                  className="-mx-2 flex items-center gap-3 rounded-md px-2 py-3 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-base text-slate-900">{p.prompt}</span>
                    <span className="block truncate text-sm text-slate-600">
                      {t(`difficulty_${p.difficulty}`)}
                      {' · '}
                      {p.origin === 'own' ? t('ownSource') : `${p.notebook_title} · ${p.source_title}`}
                    </span>
                  </span>
                  <span
                    className={cn(
                      'shrink-0 text-xs',
                      p.status === 'mastered' ? 'text-emerald-700' : p.due ? 'font-medium text-mode-ink' : 'text-slate-600'
                    )}
                  >
                    {p.due ? t('dueAgain') : p.attempted ? t('status_started') : t(`status_${p.status}`)}
                  </span>
                  <ArrowRight className="size-3.5 shrink-0 text-slate-400" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function FilterChip({ active, onClick, label, count }: { active: boolean; onClick: () => void; label: string; count: number }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30',
        active ? 'border-mode/40 bg-mode/10 text-mode-ink' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
      )}
    >
      {label}
      <span className="font-mono text-xs tabular-nums text-slate-500">{count}</span>
    </button>
  )
}

export default function PracticePage() {
  return (
    <Suspense fallback={null}>
      <PracticeList />
    </Suspense>
  )
}
