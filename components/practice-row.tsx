'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { Loader2, PenLine } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { exercisesAPI, type ExerciseSummary } from '@/lib/api'
import { toRedo } from '@/lib/practice'

/** This document's practice problems, in the "from this document" list next
 *  to its cards and quiz: how many, making more, and a link to the one page
 *  that lists every problem. */
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
            {/* The problems themselves are listed in one place only. */}
            {problems.length > 0 && (
              <>
                {' · '}
                <Link href={`/dashboard/practice?notebook=${notebookId}`} className="font-medium text-mode-ink underline-offset-4 hover:underline">
                  {t('viewAll')} →
                </Link>
              </>
            )}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button onClick={() => void make()} disabled={disabled || making} variant={problems.length ? 'outline' : 'default'}>
            {making ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {making ? t('making') : problems.length ? t('makeMore') : t('make')}
          </Button>
        </div>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}

    </div>
  )
}
