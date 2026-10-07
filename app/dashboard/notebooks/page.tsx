'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/page-header'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import useSWR, { mutate } from 'swr'
import { notebooksAPI } from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'
import { useAutoUpload } from '@/components/auto-upload'
import { useTranslations } from 'next-intl'
import {
  AlertCircle,
  Loader2,
  Plus,
  Trash2,
  Users,
} from 'lucide-react'

type NotebookItem = {
  id: number
  title: string
  description?: string
  source_count?: number
  member_count?: number
  is_owner?: boolean
  sources?: { id: number; title: string; file_type?: string }[]
  updated_at: string
}

/** A short tag for what a source is, so a cover says where the notebook's
 *  material comes from. Matches Source.FILE_TYPE_CHOICES on the backend. */
function fileTag(type?: string): string {
  switch (type) {
    case 'pdf': return 'PDF'
    case 'docx': return 'DOC'
    case 'pptx': return 'PPT'
    case 'url': return 'WEB'
    case 'text': return 'TXT'
    default: return ''
  }
}

export default function NotebooksListPage() {
  const router = useRouter()
  const [showCreate, setShowCreate] = useState(false)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const t = useTranslations('notebooks')
  const nav = useTranslations('nav')
  const common = useTranslations('common')
  const [confirm, confirmDialog] = useConfirm()
  const [error, setError] = useState('')

  const { data, isLoading, error: loadError } = useSWR(['/notebooks/'], () => notebooksAPI.getNotebooks())
  const notebooks: NotebookItem[] = data?.data?.results ?? data?.data ?? []
  // A failed fetch (backend down / network) must NOT look like an empty list —
  // otherwise a stopped server appears as "your notebooks vanished".
  const unreachable = !!loadError && !data
  // Files dropped here are placed in the notebook for their subject; only the
  // student's own notebooks can receive one.
  const upload = useAutoUpload({
    ownNotebooks: notebooks.filter((nb) => nb.is_owner !== false),
    onChanged: () => mutate(['/notebooks/']),
  })

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    setError('')
    try {
      const res = await notebooksAPI.createNotebook({
        title: title.trim(),
        description: description.trim() || undefined,
      })
      setTitle('')
      setDescription('')
      setShowCreate(false)
      mutate(['/notebooks/'])
      router.push(`/dashboard/notebooks/${res.data.id}`)
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } }
      setError(ax.response?.data?.detail || t('createFailed'))
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (e: React.MouseEvent, nb: NotebookItem) => {
    e.preventDefault()
    e.stopPropagation()
    const ok = await confirm({
      title: t('deleteTitle', { title: nb.title }),
      body: t('deleteBody'),
      confirmLabel: t('deleteConfirm'),
      cancelLabel: common('cancel'),
    })
    if (!ok) return
    setDeletingId(nb.id)
    setError('')
    try {
      await notebooksAPI.deleteNotebook(nb.id)
      mutate(['/notebooks/'])
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } }
      setError(ax.response?.data?.detail || t('deleteFailed'))
    } finally {
      setDeletingId(null)
    }
  }

  const sourceCount = (nb: NotebookItem) =>
    nb.source_count ?? (Array.isArray(nb.sources) ? nb.sources.length : 0)

  return (
    <div className="mx-auto w-full max-w-5xl space-y-8 px-4 py-6 md:px-10 md:py-10">
      {confirmDialog}
      <PageHeader
        title={nav('notebooks')}
        lead={t('lead')}
        action={
          <div className="flex flex-wrap gap-2">
            {upload.trigger}
            <Button onClick={() => setShowCreate(!showCreate)} size="lg" aria-expanded={showCreate}>
              <Plus aria-hidden />
              {t('newNotebook')}
            </Button>
          </div>
        }
      />

      {upload.results}

      {error && (
        <div role="alert" className="flex gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
          <AlertCircle className="size-5 shrink-0 text-mode-danger" aria-hidden />
          <p className="text-base text-red-700">{error}</p>
        </div>
      )}

      {showCreate && (
        <form onSubmit={handleCreate} className="sheet space-y-4 p-6">
          <div className="space-y-2">
            <Label htmlFor="nb-title">{t('name')}</Label>
            <Input
              id="nb-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('namePlaceholder')}
              required
              autoFocus
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="nb-desc">{t('description')}</Label>
            <Input
              id="nb-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('descriptionPlaceholder')}
            />
          </div>
          <div className="flex gap-3 pt-1">
            <Button type="submit" disabled={creating || !title.trim()}>
              {creating ? (
                <>
                  <Loader2 className="animate-spin" aria-hidden />
                  {t('creating')}
                </>
              ) : (
                t('createAndOpen')
              )}
            </Button>
            <Button type="button" variant="outline" onClick={() => setShowCreate(false)}>
              {common('cancel')}
            </Button>
          </div>
        </form>
      )}

      {isLoading ? (
        <ul className="grid gap-5 [grid-template-columns:repeat(auto-fill,minmax(240px,1fr))]" aria-busy>
          {[0, 1, 2].map((i) => (
            <li key={i} className="h-40 rounded-xl bg-slate-100" />
          ))}
        </ul>
      ) : unreachable ? (
        <div className="sheet flex flex-col items-start gap-4 border-amber-200 p-8">
          <p className="text-lg font-semibold text-slate-900">{t('unreachableTitle')}</p>
          <p className="max-w-[55ch] text-slate-600">{t('unreachableBody')}</p>
          <Button onClick={() => mutate(['/notebooks/'])} variant="outline">
            {t('retry')}
          </Button>
        </div>
      ) : notebooks.length === 0 ? (
        <div className="sheet flex flex-col items-start gap-4 p-8 md:p-10">
          <p className="text-lg font-semibold text-slate-900">{t('emptyTitle')}</p>
          <p className="max-w-[55ch] text-slate-600">{t('emptyBody')}</p>
          <p className="max-w-[55ch] text-slate-600">{t('emptyUploadHint')}</p>
          <Button onClick={() => setShowCreate(true)} size="lg">
            <Plus aria-hidden />
            {t('createFirst')}
          </Button>
        </div>
      ) : (
        /* Covers on a shelf: the spine on the top edge is the section's
           colour; everything else is the notebook's own words. */
        <ul className="grid gap-5 [grid-template-columns:repeat(auto-fill,minmax(240px,1fr))]">
          {notebooks.map((nb) => (
            <li key={nb.id} className="group relative">
              <Link
                href={`/dashboard/notebooks/${nb.id}`}
                className="relative flex h-full min-h-40 flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sheet transition-[box-shadow,border-color] duration-200 hover:border-mode/50 hover:shadow-lift focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
              >
                <span className="absolute left-5 -top-px h-[3px] w-10 rounded-b-full bg-mode" aria-hidden />
                <h3 className="mt-1 font-display text-xl font-semibold leading-snug text-slate-900 text-balance line-clamp-2">
                  {nb.title}
                </h3>
                {nb.description && (
                  <p className="mt-1.5 text-sm text-slate-600 line-clamp-2">{nb.description}</p>
                )}
                {/* The spine text: what is inside, in the notebook's own words. */}
                {Array.isArray(nb.sources) && nb.sources.length > 0 ? (
                  <ul className="mt-3 space-y-1 text-sm text-slate-700">
                    {nb.sources.slice(0, 3).map((src) => (
                      <li key={src.id} className="flex min-w-0 items-baseline gap-2">
                        <span className="w-8 shrink-0 font-mono text-[11px] font-medium text-slate-500">
                          {fileTag(src.file_type)}
                        </span>
                        <span className="truncate">{src.title}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 text-sm text-slate-500">{t('noSourcesYet')}</p>
                )}
                {/* The list above already shows up to three sources, so a
                    count only says something when some are not shown. An
                    empty footer would still take its padding, so it is only
                    rendered when it has something to say. */}
                {(!Array.isArray(nb.sources) || sourceCount(nb) > 3 || (nb.member_count ?? 1) > 1) && (
                <p className="mt-auto pt-4 text-sm text-slate-500">
                  {Array.isArray(nb.sources)
                    ? sourceCount(nb) > 3 && t('moreSources', { count: sourceCount(nb) - 3 })
                    : common('sources', { count: sourceCount(nb) })}
                  {(nb.member_count ?? 1) > 1 && (
                    <span className="mt-0.5 flex items-center gap-1.5 text-slate-600">
                      <Users className="size-3.5" aria-hidden />
                      {t('sharedWith', { count: (nb.member_count ?? 1) - 1 })}
                    </span>
                  )}
                </p>
                )}
              </Link>
              {/* Deleting is rare: a quiet control that appears on hover / focus. */}
              <button
                type="button"
                disabled={deletingId === nb.id}
                onClick={(e) => handleDelete(e, nb)}
                aria-label={`${common('delete')}: ${nb.title}`}
                className="absolute right-3 top-3 grid size-8 place-items-center rounded-md text-slate-400 opacity-0 transition-opacity hover:bg-red-50 hover:text-mode-danger focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-red-500/30 group-hover:opacity-100 disabled:opacity-100"
              >
                {deletingId === nb.id ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Trash2 className="size-4" aria-hidden />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
