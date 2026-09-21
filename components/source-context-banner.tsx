'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { notebooksAPI } from '@/lib/api'
import { parseSourceIdsParam } from '@/lib/source-utils'
import { ArrowLeft, FileText } from 'lucide-react'
import { useTranslations } from 'next-intl'

export function SourceContextBanner() {
  const t = useTranslations('notebooks')
  const nav = useTranslations('nav')
  const common = useTranslations('common')
  const searchParams = useSearchParams()
  const sourceParam = searchParams.get('source')
  const sourceIds = parseSourceIdsParam(sourceParam)
  const [labels, setLabels] = useState<string[]>([])

  useEffect(() => {
    if (sourceIds.length === 0) {
      setLabels([])
      return
    }
    Promise.all(
      sourceIds.map((id) =>
        notebooksAPI
          .getSource(id)
          .then((res) => res.data.title as string)
          .catch(() => t('sourceFallback', { id }))
      )
    ).then(setLabels)
  }, [sourceParam, sourceIds.join(',')])

  if (!sourceParam || sourceIds.length === 0) return null

  const label =
    labels.length > 0
      ? labels.length <= 2
        ? labels.join(', ')
        : `${labels.slice(0, 2).join(', ')} +${labels.length - 2}`
      : common('sources', { count: sourceIds.length })

  return (
    <p className="mb-4 flex min-w-0 items-center gap-2 text-sm text-slate-600">
      <FileText className="size-4 shrink-0 text-slate-500" aria-hidden />
      <span className="shrink-0">{sourceIds.length > 1 ? t('combinedSources') : t('fromSource')}:</span>
      <span className="min-w-0 truncate font-medium text-slate-900">{label}</span>
      <Link href="/dashboard/notebooks" className="ml-auto inline-flex shrink-0 items-center gap-1 font-medium text-mode hover:underline">
        <ArrowLeft className="size-4" aria-hidden />
        {nav('notebooks')}
      </Link>
    </p>
  )
}
