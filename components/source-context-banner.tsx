'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { notebooksAPI } from '@/lib/api'
import { parseSourceIdsParam } from '@/lib/source-utils'
import { ArrowLeft, FileText } from 'lucide-react'

export function SourceContextBanner() {
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
          .catch(() => `Source #${id}`)
      )
    ).then(setLabels)
  }, [sourceParam, sourceIds.join(',')])

  if (!sourceParam || sourceIds.length === 0) return null

  const label =
    labels.length > 0
      ? labels.length <= 2
        ? labels.join(' · ')
        : `${labels.slice(0, 2).join(' · ')} +${labels.length - 2} more`
      : `${sourceIds.length} source${sourceIds.length > 1 ? 's' : ''}`

  return (
    <div className="mb-6 flex items-center gap-4 rounded-xl border border-mode-library/25 bg-mode-library/5 px-5 py-4">
      <FileText className="size-6 text-mode-library shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="font-mono text-xs uppercase tracking-wide text-mode-library/80">
          {sourceIds.length > 1 ? 'Combined sources' : 'From source'}
        </p>
        <p className="text-lg font-medium text-slate-900 truncate">{label}</p>
      </div>
      <Link
        href="/dashboard/notebooks"
        className="text-base text-mode-library hover:text-mode-library-hover flex items-center gap-1 shrink-0"
      >
        <ArrowLeft className="size-5" />
        Notebooks
      </Link>
    </div>
  )
}
