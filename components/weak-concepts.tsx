'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Loader2, Target } from 'lucide-react'
import { mockTestsAPI, type WeakConcept } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { InPageLanguage, useInPageLanguage } from '@/components/in-page-language'

/** What the student keeps missing in one notebook, named, with a way to
 *  practise each concept: a fresh quiz written from the passages the missed
 *  questions came from. `refreshKey` re-fetches after a sitting is marked. */
const SHOWN = 3

export function WeakConcepts({ notebook, refreshKey }: { notebook: number; refreshKey: unknown }) {
  const t = useTranslations('tests')
  const router = useRouter()
  const [state, setState] = useState<{ notebook: number; concepts: WeakConcept[] } | null>(null)
  const [practising, setPractising] = useState<string | null>(null)
  const [error, setError] = useState('')
  // Three is what fits a glance; the rest fold away until asked for.
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    let cancelled = false
    mockTestsAPI
      .weakConcepts(notebook)
      .then((res) => {
        if (!cancelled) setState({ notebook, concepts: res.data.concepts })
      })
      .catch(() => {
        /* the row simply stays absent */
      })
    return () => {
      cancelled = true
    }
  }, [notebook, refreshKey])

  const concepts = state && state.notebook === notebook ? state.concepts : null
  const found = useInPageLanguage((concepts ?? []).flatMap((c) => [c.label, c.sample[0]]))
  if (!concepts || concepts.length === 0) return null
  const shown = showAll ? concepts : concepts.slice(0, SHOWN)
  const hidden = concepts.length - shown.length

  const practise = async (c: WeakConcept) => {
    setPractising(c.key)
    setError('')
    try {
      const res = await mockTestsAPI.practiceConcept({
        notebook,
        question_ids: c.question_ids,
        label: c.label,
        key: c.key,
      })
      router.push(`/dashboard/quizzes?source=${res.data.source_ids.join(',')}&quiz=${res.data.quiz_id}`)
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail || t('practiceFailed'))
      setPractising(null)
    }
  }

  return (
    <div className="border-t border-slate-200 pt-4 space-y-3">
      <div className="flex items-center gap-2">
        <Target className="size-4 text-mode" aria-hidden />
        <p className="text-base text-slate-700">{t('weakConcepts')}</p>
      </div>
      <ul className="space-y-2">
        {shown.map((c) => (
          <li key={c.key} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
            <div className="min-w-0 flex-1 basis-64">
              <p className="text-base text-slate-900">
                <InPageLanguage text={c.label} found={found} />
                <span className="ml-2 font-mono text-xs text-slate-500 tabular-nums">
                  {t('conceptMissed', { count: c.count })}
                </span>
              </p>
              <p className="text-sm text-slate-500 line-clamp-1">{c.sample[0] && <InPageLanguage text={c.sample[0]} found={found} />}</p>
            </div>
            <Button
              type="button"
              variant="tinted"
              size="sm"
              disabled={practising !== null}
              onClick={() => void practise(c)}
              className="shrink-0"
            >
              {practising === c.key ? <Loader2 className="size-4 animate-spin mr-1.5" aria-hidden /> : null}
              {practising === c.key
                ? t('writingPractice')
                : c.practice_quiz_id
                  ? t('continuePractice')
                  : t('practise')}
            </Button>
          </li>
        ))}
      </ul>
      {(hidden > 0 || showAll) && concepts.length > SHOWN && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="text-sm text-slate-500 hover:text-slate-900 underline underline-offset-4"
        >
          {showAll ? t('showFewer') : t('showMore', { count: hidden })}
        </button>
      )}
      {practising && <p className="text-sm text-slate-500">{t('practiceNote')}</p>}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </div>
  )
}
