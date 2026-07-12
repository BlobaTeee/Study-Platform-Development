'use client'

import { use } from 'react'
import { NotebookWorkspace } from '@/components/notebook-workspace'

export default function NotebookDetailPage({
  params,
}: {
  params: Promise<{ notebookId: string }>
}) {
  const { notebookId } = use(params)
  const id = Number(notebookId)

  if (!Number.isFinite(id) || id <= 0) {
    return (
      <p className="p-8 text-center text-slate-600">Invalid notebook.</p>
    )
  }

  return <NotebookWorkspace notebookId={id} />
}
