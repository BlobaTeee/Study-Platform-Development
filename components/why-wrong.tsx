'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, Sparkles } from 'lucide-react'
import { mockTestsAPI } from '@/lib/api'

/** "Why?" under a wrong answer: a short explanation written from the
 *  passage the question came from. Asked for on demand — most reviews never
 *  need it — and kept server-side, so `initial` is set on a second look. */
export function WhyWrong({ testId, paperQuestionId, initial }: {
  testId: number
  paperQuestionId: number
  initial?: string
}) {
  const t = useTranslations('tests')
  const [text, setText] = useState(initial ?? '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const ask = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await mockTestsAPI.explain(testId, paperQuestionId)
      setText(res.data.explanation)
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail || t('whyFailed'))
    } finally {
      setLoading(false)
    }
  }

  if (text) {
    return (
      <div className="rounded-lg border border-violet-200 bg-violet-50/60 px-4 py-3">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-mode mb-1 inline-flex items-center gap-1.5">
          <Sparkles className="size-3.5" aria-hidden />
          {t('whyTitle')}
        </p>
        <p className="text-base text-slate-800 leading-relaxed">{text}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        disabled={loading}
        onClick={() => void ask()}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-mode hover:underline disabled:opacity-60"
      >
        {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Sparkles className="size-4" aria-hidden />}
        {loading ? t('whyLoading') : t('whyButton')}
      </button>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </div>
  )
}
