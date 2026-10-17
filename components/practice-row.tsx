'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { ArrowRight, Loader2, PenLine } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { exercisesAPI, type ExerciseSummary } from '@/lib/api'
import { toRedo } from '@/lib/practice'
import { cn } from '@/lib/utils'

/** This document's practice problems, in the "from this document" list next
 *  to its cards and quiz: what exists, one line each, and making more. */
export function PracticeRow({ notebookId, sourceId, disabled }: { notebookId: number; sourceId: number; disabled?: boolean }) {
  const t = useTranslations('practice')
  const router = useRouter()
  const { data, mutate } = useSWR(['/exercises', 'source', sourceId], () => exercisesAPI.list({ source: sourceId }))
  const problems: ExerciseSummary[] = data?.data?.results ?? []
  const [making, setMaking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const redo = toRedo(problems)

  const make = async () => {
    setMaking(true)
    setError(null)
    try {
      const res = await exercisesAPI.generate(sourceId)
      await mutate()
      const first = res.data.results[0]
      if (problems.length === 0 && first) router.push(`/dashboard/practice/${first.id}`)
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      setError(typeof detail === 'string' ? detail : t('makeFailed'))
    } finally {
      setMaking(false)
    }
  }

  return (
    <div data-mode="quizzes" className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1 basis-48">
          <p className="flex items-center gap-2 text-base font-semibold text-slate-900">
            <PenLine className="size-4 text-mode" aria-hidden />
            {t('title')}
          </p>
          <p className="mt-0.5 text-sm text-slate-600">
            {problems.length === 0
              ? t('rowLead')
              : redo > 0
                ? `${t('count', { count: problems.length })} · ${t('toRedo', { count: redo })}`
                : t('count', { count: problems.length })}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button asChild variant="ghost">
            <Link href={`/dashboard/practice/new?notebook=${notebookId}`}>{t('own')}</Link>
          </Button>
          <Button onClick={() => void make()} disabled={disabled || making} variant={problems.length ? 'outline' : 'default'}>
            {making ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {making ? t('making') : problems.length ? t('makeMore') : t('make')}
          </Button>
        </div>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}

      {problems.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-100 border-t border-slate-100">
          {problems.map((p) => (
            <li key={p.id}>
              <Link
                href={`/dashboard/practice/${p.id}`}
                className="-mx-2 flex items-center gap-3 rounded-md px-2 py-2.5 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
              >
                <span className="w-10 shrink-0 text-xs text-slate-600">{t(`difficulty_${p.difficulty}`)}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-slate-900">{p.prompt}</span>
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
    </div>
  )
}
