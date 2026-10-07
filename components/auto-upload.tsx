'use client'

import { useRef, useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { AlertCircle, Check, Loader2, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { notebooksAPI, type AutoUploadResult } from '@/lib/api'
import { SOURCE_ACCEPT } from '@/lib/source-utils'

type Row = {
  key: string
  name: string
  status: 'waiting' | 'uploading' | 'done' | 'failed'
  result?: AutoUploadResult
  error?: string
  /** The move menu is open on this row. */
  moving?: boolean
}

const NEW = '__new__'

/** Upload from the notebooks page: each file goes to the notebook for its
 *  subject, one is made when there is none, and a misplaced file is moved
 *  with one choice. Files go up one after another, so a second file of a
 *  subject the first one just started lands in that same new notebook. */
export function useAutoUpload({
  ownNotebooks,
  onChanged,
}: {
  ownNotebooks: { id: number; title: string }[]
  onChanged: () => void
}): { trigger: React.ReactNode; results: React.ReactNode } {
  const t = useTranslations('notebooks')
  const common = useTranslations('common')
  const input = useRef<HTMLInputElement>(null)
  const [rows, setRows] = useState<Row[]>([])
  const busy = rows.some((r) => r.status === 'waiting' || r.status === 'uploading')

  const patch = (key: string, change: Partial<Row>) =>
    setRows((all) => all.map((r) => (r.key === key ? { ...r, ...change } : r)))

  const uploadAll = async (files: File[]) => {
    const batch: Row[] = files.map((f, i) => ({ key: `${Date.now()}-${i}-${f.name}`, name: f.name, status: 'waiting' }))
    setRows(batch)
    for (const row of batch) {
      patch(row.key, { status: 'uploading' })
      try {
        const res = await notebooksAPI.autoUpload(files[batch.indexOf(row)])
        patch(row.key, { status: 'done', result: res.data })
      } catch (err: unknown) {
        const ax = err as { response?: { data?: { detail?: string } } }
        patch(row.key, { status: 'failed', error: ax.response?.data?.detail || t('uploadFailed') })
      }
      onChanged()
    }
  }

  const move = async (row: Row, choice: string, newTitle?: string) => {
    if (!row.result) return
    const from = row.result.notebook.id
    // Drop the notebook it leaves only when this upload made it and no
    // other file of the batch went there: a notebook the student made is
    // never removed from here.
    const dropEmpty = row.result.created_notebook &&
      !rows.some((r) => r.key !== row.key && r.result?.notebook.id === from)
    try {
      const res = await notebooksAPI.moveSource(row.result.source.id, {
        ...(choice === NEW ? { new_notebook_title: newTitle } : { notebook_id: Number(choice) }),
        drop_empty_notebook: dropEmpty,
      })
      patch(row.key, {
        moving: false,
        result: { ...row.result, notebook: res.data.notebook, created_notebook: false },
      })
      onChanged()
    } catch {
      patch(row.key, { moving: false, error: t('moveFailed') })
    }
  }

  const trigger = (
    <>
      <input
        ref={input}
        type="file"
        multiple
        accept={SOURCE_ACCEPT}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          e.target.value = ''
          if (files.length) void uploadAll(files)
        }}
      />
      <Button variant="outline" size="lg" disabled={busy} onClick={() => input.current?.click()}>
        {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Upload aria-hidden />}
        {t('autoUpload')}
      </Button>
    </>
  )

  const results = rows.length === 0 ? null : (
        <section aria-live="polite" aria-label={t('autoUploadResults')} className="sheet divide-y divide-slate-100 p-2">
          <p className="px-3 py-2 text-sm text-slate-600">{t('autoUploadLead')}</p>
          {rows.map((row) => (
            <div key={row.key} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5">
              <span className="shrink-0">
                {row.status === 'done' ? (
                  <Check className="size-4 text-emerald-700" aria-hidden />
                ) : row.status === 'failed' ? (
                  <AlertCircle className="size-4 text-mode-danger" aria-hidden />
                ) : (
                  <Loader2 className={row.status === 'uploading' ? 'size-4 animate-spin text-slate-500' : 'size-4 text-slate-300'} aria-hidden />
                )}
              </span>
              <span className="min-w-0 flex-1 basis-48 truncate text-base text-slate-900">{row.name}</span>

              {row.status === 'failed' && <span className="text-sm text-red-700">{row.error}</span>}
              {(row.status === 'waiting' || row.status === 'uploading') && (
                <span className="text-sm text-slate-500">{row.status === 'uploading' ? t('placing') : t('waiting')}</span>
              )}

              {row.status === 'done' && row.result && !row.moving && (
                <span className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-slate-500" aria-hidden>→</span>
                  <Link href={`/dashboard/notebooks/${row.result.notebook.id}`} className="font-medium text-slate-900 underline-offset-4 hover:underline">
                    {row.result.notebook.title}
                  </Link>
                  {row.result.created_notebook && <span className="text-slate-500">{t('newNotebookTag')}</span>}
                  <Button variant="ghost" size="sm" onClick={() => patch(row.key, { moving: true })}>
                    {t('change')}
                  </Button>
                </span>
              )}

              {row.status === 'done' && row.result && row.moving && (
                <MoveChoice
                  current={row.result.notebook.id}
                  notebooks={ownNotebooks}
                  onCancel={() => patch(row.key, { moving: false })}
                  onChoose={(choice, title) => void move(row, choice, title)}
                  labels={{ to: t('moveTo'), newNotebook: t('newNotebookOption'), name: t('name'), save: common('save'), cancel: common('cancel') }}
                />
              )}
            </div>
          ))}
        </section>
  )

  return { trigger, results }
}

function MoveChoice({
  current, notebooks, onChoose, onCancel, labels,
}: {
  current: number
  notebooks: { id: number; title: string }[]
  onChoose: (choice: string, newTitle?: string) => void
  onCancel: () => void
  labels: { to: string; newNotebook: string; name: string; save: string; cancel: string }
}) {
  const [choice, setChoice] = useState<string>('')
  const [title, setTitle] = useState('')
  const field = 'h-9 rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-900 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30'
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (choice === NEW ? title.trim() : choice) onChoose(choice, title.trim())
      }}
    >
      <label className="sr-only" htmlFor={`move-${current}`}>{labels.to}</label>
      <select id={`move-${current}`} autoFocus value={choice} onChange={(e) => setChoice(e.target.value)} className={field}>
        <option value="" disabled>{labels.to}</option>
        {notebooks.filter((nb) => nb.id !== current).map((nb) => (
          <option key={nb.id} value={nb.id}>{nb.title}</option>
        ))}
        <option value={NEW}>{labels.newNotebook}</option>
      </select>
      {choice === NEW && (
        <input aria-label={labels.name} value={title} onChange={(e) => setTitle(e.target.value)} className={`${field} w-44`} placeholder={labels.name} />
      )}
      <Button type="submit" size="sm" disabled={!(choice === NEW ? title.trim() : choice)}>{labels.save}</Button>
      <Button type="button" size="sm" variant="ghost" onClick={onCancel}>{labels.cancel}</Button>
    </form>
  )
}
