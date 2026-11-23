'use client'

import { Suspense, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { ArrowRight, FileText, Pencil } from 'lucide-react'
import { OwnProblemForm } from '@/components/own-problem-form'
import { PageHeader } from '@/components/page-header'
import { InPageLanguage, useInPageLanguage } from '@/components/in-page-language'
import { exercisesAPI, type ExerciseSummary } from '@/lib/api'
import { filtered, filtersFor, inPracticeOrder, parseFilter, practiceRows, type PracticeFilter } from '@/lib/practice'
import { Button } from '@/components/ui/button'
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
  const { data, isLoading, mutate } = useSWR(['/exercises', 'all'], () => exercisesAPI.list({}))
  const all: ExerciseSummary[] = data?.data?.results ?? []
  const filters = filtersFor(all)
  const shown = inPracticeOrder(filtered(all, filter))
  const rows = practiceRows(shown)
  const found = useInPageLanguage(shown.map((p) => p.prompt))
  const [writing, setWriting] = useState(filter === 'own')
  const [renaming, setRenaming] = useState<string | null>(null)

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
        {filter === 'all' ? (
          <p className="max-w-[65ch] text-sm text-slate-600">{t('pageLead')}</p>
        ) : (
          // Reached from a notebook (or the own-problem filter): say it is one
          // slice of the same list, with the way back to all of it.
          <p className="max-w-[65ch] text-sm text-slate-600">
            {t('viewing', {
              name: filter === 'own'
                ? t('filterOwn')
                : filters.find((f) => f.key === filter)?.title || t('viewingThisNotebook'),
            })}
            {' · '}
            <button
              type="button"
              onClick={() => pick('all')}
              className="font-medium text-mode-ink underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
            >
              {t('showAll')}
            </button>
          </p>
        )}

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
            {rows.map((row) => {
              if (row.kind === 'set') {
                const all = row.done === row.problems.length
                if (renaming === row.key) {
                  return <RenameSet key={row.key} setKey={row.key} title={row.title} onDone={() => { setRenaming(null); void mutate() }} />
                }
                return (
                  <ListRow
                    key={row.key}
                    href={`/dashboard/practice/${row.next.id}`}
                    icon
                    title={row.title || t('setUntitled')}
                    meta={t('setMeta', { count: row.problems.length, done: row.done })}
                    status={all ? t('status_mastered') : row.due ? t('dueAgain') : row.started ? t('status_started') : t('status_new')}
                    tone={all ? 'done' : row.due ? 'due' : 'plain'}
                    action={
                      <Button type="button" variant="ghost" size="icon-sm" onClick={() => setRenaming(row.key)}
                              aria-label={t('renameSet')} title={t('renameSet')}>
                        <Pencil aria-hidden />
                      </Button>
                    }
                  />
                )
              }
              const p = row.problem
              return (
                <ListRow
                  key={p.id}
                  href={`/dashboard/practice/${p.id}`}
                  title={<InPageLanguage text={p.prompt} found={found} />}
                  meta={`${t(`difficulty_${p.difficulty}`)} · ${p.origin === 'own' ? t('ownSource') : `${p.notebook_title} · ${p.source_title}`}`}
                  status={p.due ? t('dueAgain') : p.attempted ? t('status_started') : t(`status_${p.status}`)}
                  tone={p.status === 'mastered' ? 'done' : p.due ? 'due' : 'plain'}
                />
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}

/** One line of the list: a problem, or a set picked from one file. */
function ListRow({ href, icon, title, meta, status, tone, action }: {
  href: string; icon?: boolean; title: React.ReactNode; meta: string; status: string; tone: 'done' | 'due' | 'plain'
  action?: React.ReactNode
}) {
  return (
    <li className="flex items-center gap-1">
      <Link
        href={href}
        className="-mx-2 flex min-w-0 flex-1 items-center gap-3 rounded-md px-2 py-3 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
      >
        {icon && <FileText className="size-4 shrink-0 text-slate-500" aria-hidden />}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-base text-slate-900">{title}</span>
          <span className="block truncate text-sm text-slate-600">{meta}</span>
        </span>
        <span
          className={cn(
            'shrink-0 text-xs',
            tone === 'done' ? 'text-emerald-700' : tone === 'due' ? 'font-medium text-mode-ink' : 'text-slate-600'
          )}
        >
          {status}
        </span>
        <ArrowRight className="size-3.5 shrink-0 text-slate-400" aria-hidden />
      </Link>
      {action}
    </li>
  )
}

/** A set's name, changed in place of its line. */
function RenameSet({ setKey, title, onDone }: { setKey: string; title: string; onDone: () => void }) {
  const t = useTranslations('practice')
  const [value, setValue] = useState(title)
  const [saving, setSaving] = useState(false)
  const [failed, setFailed] = useState(false)

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setFailed(false)
    try {
      await exercisesAPI.renameSet(setKey, value.trim())
      onDone()
    } catch {
      setFailed(true)
      setSaving(false)
    }
  }

  return (
    <li className="py-3">
      <form onSubmit={save} className="flex flex-wrap items-center gap-2">
        <label htmlFor={`rename-${setKey}`} className="sr-only">{t('renameSet')}</label>
        <input
          id={`rename-${setKey}`}
          autoFocus
          value={value}
          maxLength={200}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Escape') onDone() }}
          placeholder={t('setUntitled')}
          className="h-9 min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
        />
        <Button type="submit" size="sm" disabled={saving}>{t('renameSave')}</Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone} disabled={saving}>{t('renameCancel')}</Button>
      </form>
      {failed && <p role="alert" className="mt-1 text-sm text-red-700">{t('renameFailed')}</p>}
    </li>
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
