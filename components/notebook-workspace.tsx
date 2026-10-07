'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import useSWR, { mutate } from 'swr'
import { notebooksAPI } from '@/lib/api'
import {
  SOURCE_ACCEPT,
  fileTypeLabel,
  type SourceKind,
  formatSourceIdsForQuery,
  isAllowedSourceFile,
  titleFromFileName,
} from '@/lib/source-utils'
import { SourceDropZone } from '@/components/source-drop-zone'
import { useConfirm } from '@/components/confirm-dialog'
import { NotebookMembers } from '@/components/notebook-members'
import {
  AlertCircle,
  ArrowLeft,
  ChevronDown,
  ClipboardPaste,
  Link2,
  FileUp,
  HelpCircle,
  Loader2,
  Zap,
  Download,
  Pencil,
  Plus,
  Users,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslations } from 'next-intl'

type SourceItem = {
  id: number
  title: string
  file_type?: SourceKind
  original_filename: string
  page_count: number
  status: string
  gemini_summary: string
}


/** A button that opens a short list of actions. Closes on an outside click
 *  or Escape; items are plain buttons so they keep their focus ring. */
function ActionMenu({ label, icon, items, align = 'right' }: {
  label: string
  icon?: React.ReactNode
  items: { key: string; label: string; icon?: React.ReactNode; onSelect: () => void; disabled?: boolean }[]
  align?: 'left' | 'right'
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <div ref={ref} className="relative">
      <Button type="button" variant="outline" size="sm" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {icon}
        {label}
        <ChevronDown className={cn('transition-transform duration-150 motion-reduce:transition-none', open && 'rotate-180')} aria-hidden />
      </Button>
      {open && (
        <div
          role="menu"
          className={cn(
            'absolute top-full z-30 mt-1.5 w-52 rounded-lg border border-slate-200 bg-white p-1 shadow-lift',
            align === 'right' ? 'right-0' : 'left-0'
          )}
        >
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              onClick={() => { setOpen(false); item.onSelect() }}
              className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-slate-800 hover:bg-slate-100 focus-visible:bg-slate-100 focus-visible:outline-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:text-slate-500"
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/** What an exact set of documents already has: its cards, how many of them
 *  were never studied, and a quiz. Counted server-side on the same set a
 *  generate press adds to. */
function useMaterialCounts(notebookId: number, ids: number[]) {
  const query = formatSourceIdsForQuery(ids)
  const { data } = useSWR(
    ids.length > 0 ? ['/notebooks/material_counts', notebookId, query] : null,
    () => notebooksAPI.getMaterialCounts(notebookId, ids)
  )
  const cards: number = data?.data?.flashcards ?? 0
  const unseen: number = data?.data?.unseen ?? 0
  const quizId: number | null = data?.data?.quiz_id ?? null
  return { query, cards, unseen, quizId }
}

/** Must match MAX_CARDS_PER_SOURCE in backend/notebooks/services/deck_limits.py. */
const MAX_UNSTARTED_CARDS = 10

export function NotebookWorkspace({ notebookId }: { notebookId: number }) {
  const router = useRouter()
  const t = useTranslations('notebooks')
  const common = useTranslations('common')
  const nav = useTranslations('nav')
  // How long a document is, in the reader's language: pages for a PDF,
  // slides for a deck, nothing for formats without a page count.
  const lengthLabel = (fileType: string | undefined, count: number | undefined) =>
    !count || count <= 0 ? null
      : fileType === 'pptx' ? t('slides', { count })
      : fileType === 'pdf' ? t('pages', { count })
      : null
  const [generating, setGenerating] = useState<'flashcards' | 'quiz' | null>(null)
  const [checkedSourceIds, setCheckedSourceIds] = useState<number[]>([])
  const [activeSourceId, setActiveSourceId] = useState<number | null>(null)
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploading, setUploading] = useState(false)
  // A source without a file: pasted text or a link. One small inline form,
  // one of two shapes, so a first-time visitor with nothing to upload still
  // gets to a deck in under a minute.
  const [composer, setComposer] = useState<'text' | 'url' | null>(null)
  const [composerBody, setComposerBody] = useState('')
  const [error, setError] = useState('')
  // Renaming: null when not editing, else the draft title.
  const [titleDraft, setTitleDraft] = useState<string | null>(null)
  const [renaming, setRenaming] = useState(false)
  const [exporting, setExporting] = useState<'flashcards' | 'questions' | null>(null)
  // Who is in this notebook; the chat itself lives in the corner launcher.
  const [panel, setPanel] = useState<'members' | null>(null)
  // Set when generation silently degraded to the extractive fallback, so a
  // lower-quality result is never mistaken for the real generator's output.
  const [warning, setWarning] = useState('')
  const [deletingSourceId, setDeletingSourceId] = useState<number | null>(null)
  const [confirm, confirmDialog] = useConfirm()
  const [loadingSource, setLoadingSource] = useState(false)
  const [sourceDetail, setSourceDetail] = useState<{
    // Only the opening of the document; `text_length` is how long the whole
    // thing is, so the reader can say what it is not showing.
    text_preview: string
    text_length: number
    gemini_summary: string
    title: string
    page_count: number
    status: string
    error_message?: string
  } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const swrKey = ['/notebooks/', notebookId]
  const { data: notebookRes, isLoading, error: loadError } = useSWR(swrKey, () =>
    notebooksAPI.getNotebook(notebookId)
  )

  const notebook = notebookRes?.data
  const sources: SourceItem[] = notebook?.sources ?? []

  // Two scopes, never guessed between: the document being read (its own
  // actions sit in the reader) and the documents ticked in the list (their
  // actions sit in the selection bar). One used to stand in for the other,
  // so the button under document A could quietly generate from A and B.
  const isReady = (id: number) => sources.find((x) => x.id === id)?.status === 'ready'
  const selectedIds = useMemo(
    () => checkedSourceIds.filter(isReady),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [checkedSourceIds, sources]
  )
  const activeIds = useMemo(
    () => (activeSourceId && isReady(activeSourceId) ? [activeSourceId] : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeSourceId, sources]
  )
  const activeCounts = useMaterialCounts(notebookId, activeIds)
  const selectedCounts = useMaterialCounts(notebookId, selectedIds)

  const readySources = sources.filter((s) => s.status === 'ready')

  const refresh = () => {
    mutate(swrKey)
    mutate(['/notebooks/'])
  }

  useEffect(() => {
    setActiveSourceId(null)
    setCheckedSourceIds([])
    setSourceDetail(null)
  }, [notebookId])

  // `?source=<id>` — a mock-test review's "Open in notebook" lands here and
  // should open that document, not the empty state. Only on arrival: once
  // the student clicks another document the URL no longer decides.
  const searchParams = useSearchParams()
  const requestedSourceId = Number(searchParams.get('source')) || null
  // Otherwise the first document opens: a notebook with material should
  // never greet its owner with "add a document".
  useEffect(() => {
    if (activeSourceId !== null || sources.length === 0) return
    const wanted = requestedSourceId && sources.some((s) => s.id === requestedSourceId)
      ? requestedSourceId
      : sources[0].id
    setActiveSourceId(wanted)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedSourceId, sources.length])

  const toggleSourceCheck = (id: number) => {
    setCheckedSourceIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const selectAllReady = () => {
    setCheckedSourceIds(readySources.map((s) => s.id))
  }

  const clearChecked = () => setCheckedSourceIds([])

  useEffect(() => {
    if (!activeSourceId) {
      setSourceDetail(null)
      return
    }
    setLoadingSource(true)
    notebooksAPI
      .getSource(activeSourceId)
      .then((res) => {
        setSourceDetail({
          text_preview: res.data.text_preview,
          text_length: res.data.text_length,
          gemini_summary: res.data.gemini_summary,
          title: res.data.title,
          page_count: res.data.page_count,
          status: res.data.status,
          error_message: res.data.error_message,
        })
      })
      .catch(() => setSourceDetail(null))
      .finally(() => setLoadingSource(false))
  }, [activeSourceId])

  const activeListItem = sources.find((s) => s.id === activeSourceId)

  const uploadFile = async (file: File) => {
    if (!isAllowedSourceFile(file)) {
      setError(t('unsupportedFile'))
      return
    }

    setUploading(true)
    setError('')
    try {
      const res = await notebooksAPI.uploadSource(notebookId, file, titleFromFileName(file.name))
      if (fileRef.current) fileRef.current.value = ''
      setActiveSourceId(res.data.id)
      refresh()
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } }
      setError(ax.response?.data?.detail || t('uploadFailed'))
    } finally {
      setUploading(false)
    }
  }

  const handleAddComposed = async () => {
    if (!composer || !composerBody.trim() || uploading) return
    setUploading(true)
    setError('')
    try {
      const title = uploadTitle.trim() || undefined
      const res =
        composer === 'text'
          ? await notebooksAPI.addTextSource(notebookId, { text: composerBody, title })
          : await notebooksAPI.addUrlSource(notebookId, { url: composerBody.trim(), title })
      setUploadTitle('')
      setComposerBody('')
      setComposer(null)
      setActiveSourceId(res.data.id)
      refresh()
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } }
      setError(ax.response?.data?.detail || (composer === 'text' ? t('addTextFailed') : t('addLinkFailed')))
    } finally {
      setUploading(false)
    }
  }

  const handleFileInput = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    await uploadFile(file)
  }

  const canDrop = !uploading

  // Generating adds to the selection's deck; the cards already there keep
  // their schedules, so there is nothing to confirm.
  const handleGenerateFlashcards = async (ids: number[]) => {
    if (ids.length === 0) {
      setError(t('selectToGenerateFlashcards'))
      return
    }
    const studyQuery = formatSourceIdsForQuery(ids)
    setGenerating('flashcards')
    setError('')
    setWarning('')
    try {
      const res = await notebooksAPI.generateFlashcardsFromSources(notebookId, ids)
      mutate(['/flashcards/'])
      // The deck this selection holds just changed. Matters on the fallback
      // branch below, which stays on this page.
      mutate(['/notebooks/material_counts', notebookId, studyQuery])
      if (res.data.generated_by === 'extractive-fallback') {
        setWarning(t('fallbackNotice', { kind: t('kindFlashcards') }))
        return  // stay put so the downgrade is seen, not silently navigated past
      }
      router.push(`/dashboard/flashcards?due=1&source=${studyQuery}`)
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } }
      setError(ax.response?.data?.detail || t('generateFlashcardsFailed'))
    } finally {
      setGenerating(null)
    }
  }

  const handleGenerateQuiz = async (ids: number[]) => {
    if (ids.length === 0) {
      setError(t('selectToGenerateQuiz'))
      return
    }
    const studyQuery = formatSourceIdsForQuery(ids)
    setGenerating('quiz')
    setError('')
    setWarning('')
    try {
      const res = await notebooksAPI.generateQuizFromSources(notebookId, ids)
      mutate(['/quizzes/'])
      // The "Take quiz" link reads quiz_id from the counts endpoint, so it only
      // appears once this is revalidated. Matters on the fallback branch below,
      // which stays on this page.
      mutate(['/notebooks/material_counts', notebookId, studyQuery])
      if (res.data.generated_by === 'extractive-fallback') {
        setWarning(t('fallbackNotice', { kind: t('kindQuestions') }))
        return  // stay put so the downgrade is seen, not silently navigated past
      }
      const quizId = res.data.quiz?.id
      router.push(
        quizId
          ? `/dashboard/quizzes?source=${studyQuery}&quiz=${quizId}`
          : `/dashboard/quizzes?source=${studyQuery}`
      )
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } }
      setError(ax.response?.data?.detail || t('generateQuizFailed'))
    } finally {
      setGenerating(null)
    }
  }


  const handleRemoveSource = async (sourceId: number, title: string) => {
    const ok = await confirm({
      title: t('removeTitle', { title }),
      body: t('removeBody'),
      confirmLabel: t('removeConfirm'),
    })
    if (!ok) return
    setDeletingSourceId(sourceId)
    setError('')
    try {
      await notebooksAPI.deleteSource(sourceId)
      if (activeSourceId === sourceId) {
        setActiveSourceId(null)
        setSourceDetail(null)
      }
      setCheckedSourceIds((prev) => prev.filter((id) => id !== sourceId))
      // The removed source drops out of both scopes, so the counts keyed on
      // them no longer describe anything on screen.
      mutate(['/notebooks/material_counts', notebookId, activeCounts.query])
      mutate(['/notebooks/material_counts', notebookId, selectedCounts.query])
      refresh()
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } }
      setError(ax.response?.data?.detail || t('removeFailed'))
    } finally {
      setDeletingSourceId(null)
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-10 animate-spin text-mode-library" />
      </div>
    )
  }

  if (loadError || !notebook) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
        <p className="text-lg text-slate-500">{t('notFound')}</p>
        <Button asChild variant="outline">
          <Link href="/dashboard/notebooks">
            <ArrowLeft className="size-4 mr-2" />
            {t('allNotebooks')}
          </Link>
        </Button>
      </div>
    )
  }

  const saveTitle = async () => {
    const title = (titleDraft ?? '').trim()
    if (!title || title === notebook.title) {
      setTitleDraft(null)
      return
    }
    setRenaming(true)
    setError('')
    try {
      await notebooksAPI.updateNotebook(notebook.id, { title })
      setTitleDraft(null)
      // The header reads from this key; the sidebar/list from the other.
      mutate(swrKey)
      mutate(['/notebooks/'])
    } catch {
      setError(t('renameFailed'))
    } finally {
      setRenaming(false)
    }
  }

  const exportCsv = async (kind: 'flashcards' | 'questions') => {
    setExporting(kind)
    setError('')
    try {
      const res = await notebooksAPI.exportCsv(notebook.id, kind)
      const name = /filename="?([^"]+)"?/.exec(res.headers['content-disposition'] ?? '')?.[1]
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = name ?? `${kind}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError(t('exportFailed'))
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      {confirmDialog}
      <div className="border-t-[3px] border-mode-library flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-5 md:px-6 py-4 border-b border-slate-200 shrink-0">
        <div className="min-w-0 flex-1">
          <Link
            href="/dashboard/notebooks"
            className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-mode-library mb-2"
          >
            <ArrowLeft className="size-4" />
            {t('allNotebooks')}
          </Link>
          {titleDraft !== null ? (
            <form
              className="flex flex-wrap items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                void saveTitle()
              }}
            >
              <Input
                value={titleDraft}
                onChange={(e) => setTitleDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setTitleDraft(null)
                }}
                aria-label={t('renameNotebook')}
                autoFocus
                maxLength={200}
                className="h-11 text-xl font-display font-semibold basis-full sm:basis-auto sm:flex-1"
              />
              <Button type="submit" size="lg" className="h-11 bg-mode-library hover:bg-mode-library-hover text-white" disabled={renaming || !titleDraft.trim()}>
                {common('save')}
              </Button>
              <Button type="button" size="lg" variant="outline" className="h-11" disabled={renaming} onClick={() => setTitleDraft(null)}>
                {common('cancel')}
              </Button>
            </form>
          ) : (
            <div className="flex items-center gap-2 min-w-0">
              <h1 className="font-display text-2xl md:text-3xl font-semibold text-slate-900 truncate">
                {notebook.title}
              </h1>
              <button
                type="button"
                onClick={() => setTitleDraft(notebook.title)}
                aria-label={t('renameNotebook')}
                title={t('renameNotebook')}
                className="shrink-0 rounded-md p-1.5 text-slate-400 hover:text-slate-900 hover:bg-slate-100"
              >
                <Pencil className="size-4" aria-hidden />
              </button>
            </div>
          )}
          {notebook.description && (
            <p className="text-base text-slate-500 mt-1 line-clamp-2">
              {notebook.description}
            </p>
          )}
        </div>
        {/* Your data, as a file: opens in Excel, imports into Anki. */}
        <div className="flex basis-full flex-wrap items-center gap-1 text-sm text-slate-600 sm:basis-auto sm:flex-nowrap">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-pressed={panel === 'members'}
            onClick={() => setPanel((p) => (p === 'members' ? null : 'members'))}
            className="mr-2"
          >
            <Users aria-hidden />
            {t('share')}
          </Button>
          <ActionMenu
            label={t('exportMenu')}
            icon={exporting ? <Loader2 className="animate-spin" aria-hidden /> : <Download aria-hidden />}
            items={[
              { key: 'cards', label: t('exportCardsCsv'), disabled: exporting !== null, onSelect: () => void exportCsv('flashcards') },
              { key: 'questions', label: t('exportQuestionsCsv'), disabled: exporting !== null, onSelect: () => void exportCsv('questions') },
            ]}
          />
        </div>
      </div>

      {panel === 'members' && (
        <NotebookMembers notebookId={notebook.id} onClose={() => setPanel(null)} />
      )}

      {error && (
        <div className="mx-5 md:mx-6 mt-4 flex gap-3 rounded-lg bg-red-50 p-3 border border-red-200 shrink-0">
          <AlertCircle className="size-5 text-mode-danger shrink-0" />
          <p className="text-base text-red-700">{error}</p>
        </div>
      )}

      {warning && (
        <div className="mx-5 md:mx-6 mt-4 flex gap-3 rounded-lg bg-amber-50 p-3 border border-amber-200 shrink-0">
          <AlertCircle className="size-5 text-amber-600 shrink-0" />
          <p className="text-base text-amber-800">{warning}</p>
        </div>
      )}

      {/* The page scrolls as one: the whole notebook's study strip first,
          then its documents. Dropping a file anywhere on it still adds it. */}
      <SourceDropZone onFile={uploadFile} disabled={!canDrop} className="flex-col overflow-y-auto bg-slate-50/60">
        <div className="mx-auto w-full max-w-6xl space-y-8 px-4 py-6 md:px-8 md:py-8">
          <section aria-labelledby="documents-heading" className="space-y-3">
            <input
              ref={fileRef}
              type="file"
              accept={SOURCE_ACCEPT}
              className="hidden"
              onChange={handleFileInput}
              disabled={uploading}
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 id="documents-heading" className="text-sm font-semibold text-slate-900">
                {t('sources')}
                <span className="ml-1.5 font-mono text-xs font-normal text-slate-600 tabular-nums">{sources.length}</span>
              </h2>
              <div className="flex items-center gap-3">
                {readySources.length > 1 && (
                  <button
                    type="button"
                    onClick={checkedSourceIds.length === readySources.length ? clearChecked : selectAllReady}
                    className="text-sm font-medium text-mode-ink hover:underline"
                  >
                    {checkedSourceIds.length === readySources.length ? t('clear') : t('selectAll')}
                  </button>
                )}
                {uploading ? (
                  <span className="inline-flex items-center gap-2 text-sm text-slate-600">
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                    {t('processing')}
                  </span>
                ) : (
                  <ActionMenu
                    label={t('addDocument')}
                    icon={<Plus aria-hidden />}
                    items={[
                      { key: 'file', label: t('browseFiles'), icon: <FileUp aria-hidden />, onSelect: () => fileRef.current?.click() },
                      { key: 'text', label: t('pasteText'), icon: <ClipboardPaste aria-hidden />, onSelect: () => setComposer('text') },
                      { key: 'url', label: t('addLink'), icon: <Link2 aria-hidden />, onSelect: () => setComposer('url') },
                    ]}
                  />
                )}
              </div>
            </div>

            {composer && (
              <form
                className="sheet space-y-3 p-4"
                onSubmit={(e) => {
                  e.preventDefault()
                  void handleAddComposed()
                }}
              >
                <Input
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  placeholder={t('titleOptional')}
                />
                {composer === 'text' ? (
                  <textarea
                    autoFocus
                    value={composerBody}
                    onChange={(e) => setComposerBody(e.target.value)}
                    placeholder={t('pastePlaceholder')}
                    rows={6}
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus-visible:border-mode focus-visible:ring-[3px] focus-visible:ring-mode/25"
                  />
                ) : (
                  <Input
                    autoFocus
                    type="url"
                    value={composerBody}
                    onChange={(e) => setComposerBody(e.target.value)}
                    placeholder={t('urlPlaceholder')}
                  />
                )}
                <div className="flex flex-wrap gap-2">
                  <Button type="submit" disabled={uploading || !composerBody.trim()}>
                    {uploading ? t('adding') : t('addSource')}
                  </Button>
                  <Button type="button" variant="outline" onClick={() => setComposer(null)}>
                    {common('cancel')}
                  </Button>
                </div>
              </form>
            )}

            <div className="sheet grid overflow-hidden md:grid-cols-[18rem_minmax(0,1fr)]">
              <aside className="flex flex-col border-b border-slate-200 bg-slate-50 md:border-b-0 md:border-r">
                <div className="flex-1 space-y-1 p-2">
                  {sources.length === 0 ? (
                    <div className="px-3 py-6 text-sm leading-relaxed text-slate-600">
                      <p>{t('dragHere')}</p>
                      <p className="mt-1 text-slate-500">{t('formatsShort')}</p>
                    </div>
                  ) : (
                    sources.map((src) => {
                      const isChecked = checkedSourceIds.includes(src.id)
                      const isActive = activeSourceId === src.id
                      return (
                        <div
                          key={src.id}
                          className={cn(
                            'group flex items-stretch rounded-lg border transition-[background-color,border-color] duration-150',
                            isActive
                              ? 'border-mode/40 bg-mode/10'
                              : isChecked
                                ? 'border-mode/20 bg-mode/5'
                                : 'border-transparent hover:bg-slate-100'
                          )}
                        >
                          <div className="flex shrink-0 items-start py-3 pl-3">
                            <input
                              type="checkbox"
                              checked={isChecked}
                              disabled={src.status !== 'ready'}
                              onChange={() => toggleSourceCheck(src.id)}
                              aria-label={`${isChecked ? t('deselectForGeneration') : t('selectForGeneration')}: ${src.title}`}
                              className="mt-1 size-4 rounded border-slate-300 accent-[var(--mode)] disabled:opacity-40"
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() => setActiveSourceId(src.id)}
                            aria-current={isActive ? 'true' : undefined}
                            className="min-w-0 flex-1 px-2 py-2.5 text-left"
                          >
                            <p className={cn('line-clamp-2 break-words text-[15px] font-medium leading-snug', isActive ? 'text-slate-900' : 'text-slate-800')}>{src.title}</p>
                            <p className="mt-0.5 text-sm text-slate-600">
                              {src.status === 'failed' ? (
                                <span className="text-red-700">{t('statusFailed')}</span>
                              ) : src.status !== 'ready' ? (
                                <span className="text-amber-700">{t('statusProcessing')}</span>
                              ) : (
                                <>
                                  {src.file_type === 'text' ? t('typeText') : src.file_type === 'url' ? t('typeLink') : fileTypeLabel(src.file_type)}
                                  {lengthLabel(src.file_type, src.page_count) ? ` · ${lengthLabel(src.file_type, src.page_count)}` : ''}
                                </>
                              )}
                            </p>
                          </button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            title={t('removeSource')}
                            disabled={deletingSourceId === src.id}
                            onClick={(e) => {
                              e.stopPropagation()
                              handleRemoveSource(src.id, src.title)
                            }}
                            className={cn(
                              'my-1 mr-1 shrink-0 text-slate-500 hover:bg-red-50 hover:text-mode-danger',
                              'opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100',
                              isActive && 'opacity-100'
                            )}
                          >
                            {deletingSourceId === src.id ? t('removing') : t('remove')}
                          </Button>
                        </div>
                      )
                    })
                  )}
                </div>

                {/* Ticked documents get their own actions, like a selection in
                    a mail client: one combined set from all of them. */}
                {selectedIds.length > 0 && (
                  <div role="region" aria-label={t('selectionSummary', { count: selectedIds.length })} className="space-y-2.5 border-t border-slate-200 bg-white p-3">
                    <div>
                      <p className="text-sm font-medium text-slate-900">{t('selectionSummary', { count: selectedIds.length })}</p>
                      <p className="mt-0.5 text-xs text-slate-600">
                        {t('selectionHint')}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        data-mode="flashcards"
                        disabled={generating !== null}
                        onClick={() => void handleGenerateFlashcards(selectedIds)}
                      >
                        {generating === 'flashcards' ? <Loader2 className="animate-spin" aria-hidden /> : null}
                        {selectedCounts.cards > 0 ? t('addFlashcards') : t('generateFlashcards')}
                      </Button>
                      <Button
                        size="sm"
                        data-mode="quizzes"
                        disabled={generating !== null}
                        onClick={() => void handleGenerateQuiz(selectedIds)}
                      >
                        {generating === 'quiz' ? <Loader2 className="animate-spin" aria-hidden /> : null}
                        {t('generateQuiz')}
                      </Button>
                    </div>
                  </div>
                )}
              </aside>

              <div className="min-w-0 bg-white p-5 md:p-8">
                {!activeSourceId || !activeListItem ? (
                  <div className="max-w-[48ch] py-6">
                    <h2 className="font-display text-2xl font-semibold text-slate-900">{t('addSourcesTitle')}</h2>
                    <p className="mt-3 text-base leading-relaxed text-slate-600">{t('addSourcesBody')}</p>
                    <Button type="button" size="lg" className="mt-6" onClick={() => fileRef.current?.click()} disabled={uploading}>
                      <FileUp aria-hidden />
                      {t('browseFiles')}
                    </Button>
                  </div>
                ) : loadingSource ? (
                  <div className="space-y-3 py-2" aria-busy>
                    <div className="h-7 w-2/3 animate-pulse rounded bg-slate-100 motion-reduce:animate-none" />
                    <div className="h-4 w-1/3 animate-pulse rounded bg-slate-100 motion-reduce:animate-none" />
                    <div className="h-24 w-full animate-pulse rounded bg-slate-100 motion-reduce:animate-none" />
                  </div>
                ) : (
                  <div className="space-y-6">
                    <div className="min-w-0">
                      <h2 className="font-display text-2xl font-semibold leading-snug text-slate-900 text-balance">
                        {sourceDetail?.title}
                      </h2>
                      <p className="mt-2 text-sm text-slate-600">
                        {activeListItem.file_type === 'url' ? (
                          <a
                            href={activeListItem.original_filename}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="break-all text-mode-library-ink hover:underline"
                          >
                            {activeListItem.original_filename}
                          </a>
                        ) : (
                          activeListItem.original_filename
                        )}
                        {activeListItem.file_type === 'text'
                          ? t('typeText')
                          : activeListItem.file_type === 'url'
                            ? ''
                            : lengthLabel(activeListItem.file_type, sourceDetail?.page_count)
                              ? ` · ${lengthLabel(activeListItem.file_type, sourceDetail?.page_count)}`
                              : ` · ${fileTypeLabel(activeListItem.file_type)}`}
                      </p>
                    </div>

                    {sourceDetail?.status === 'failed' && sourceDetail.error_message && (
                      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                        {sourceDetail.error_message}
                      </div>
                    )}

                    {sourceDetail?.gemini_summary && (
                      <div className="border-t border-slate-200 pt-5">
                        <h3 className="text-sm font-semibold text-slate-900">{t('overview')}</h3>
                        <p className="mt-2 max-w-[75ch] text-base leading-relaxed text-slate-700 hyphens-auto md:text-justify">
                          {sourceDetail.gemini_summary}
                        </p>
                      </div>
                    )}

                    {/* This document's cards and quiz: what exists, in plain words,
                        and the two things to do with it. One study button per
                        kind on the page — this is the only one. */}
                    <div className="border-t border-slate-200 pt-5">
                      <h3 className="text-sm font-semibold text-slate-900">{t('fromThisDocument')}</h3>
                      <div className="mt-3 divide-y divide-slate-200 rounded-xl border border-slate-200">
                        <div data-mode="flashcards" className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 p-4">
                          <div className="min-w-0 flex-1 basis-48">
                            <p className="flex items-center gap-2 text-base font-semibold text-slate-900">
                              <Zap className="size-4 text-mode" aria-hidden />
                              {nav('flashcards')}
                            </p>
                            <p className="mt-0.5 text-sm text-slate-600">
                              {activeCounts.cards === 0
                                ? t('noCardsForDoc')
                                : activeCounts.unseen > 0
                                  ? t('cardsNotStarted', { cards: common('cards', { count: activeCounts.cards }), count: activeCounts.unseen })
                                  : common('cards', { count: activeCounts.cards })}
                            </p>
                          </div>
                          <div className="flex shrink-0 flex-wrap gap-2">
                            {/* A full batch not yet started gets no more (the server
                                refuses it too); the way on is to study them. */}
                            {activeCounts.unseen < MAX_UNSTARTED_CARDS && (
                            <Button
                              onClick={() => void handleGenerateFlashcards(activeIds)}
                              disabled={activeIds.length === 0 || generating !== null}
                              variant={activeCounts.cards > 0 ? 'outline' : 'default'}
                            >
                              {generating === 'flashcards' && selectedIds.length === 0 ? <Loader2 className="animate-spin" aria-hidden /> : null}
                              {activeCounts.cards > 0 ? t('addFlashcards') : t('generateFlashcards')}
                            </Button>
                            )}
                            {activeCounts.cards > 0 && (
                              <Button asChild>
                                <Link href={`/dashboard/flashcards?due=1&source=${activeCounts.query}`}>
                                  {/* Part-way through the first pass: carry on where it stopped. */}
                                  {activeCounts.unseen > 0 && activeCounts.unseen < activeCounts.cards ? t('continueFlashcards') : t('studyFlashcards')}
                                </Link>
                              </Button>
                            )}
                          </div>
                        </div>
                        <div data-mode="quizzes" className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 p-4">
                          <div className="min-w-0 flex-1 basis-48">
                            <p className="flex items-center gap-2 text-base font-semibold text-slate-900">
                              <HelpCircle className="size-4 text-mode" aria-hidden />
                              {nav('quizzes')}
                            </p>
                            <p className="mt-0.5 text-sm text-slate-600">
                              {activeCounts.quizId ? t('quizReady') : t('noQuizForDoc')}
                            </p>
                          </div>
                          <div className="flex shrink-0 flex-wrap gap-2">
                            <Button
                              onClick={() => void handleGenerateQuiz(activeIds)}
                              disabled={activeIds.length === 0 || generating !== null}
                              variant={activeCounts.quizId ? 'outline' : 'default'}
                            >
                              {generating === 'quiz' && selectedIds.length === 0 ? <Loader2 className="animate-spin" aria-hidden /> : null}
                              {t('generateQuiz')}
                            </Button>
                            {activeCounts.quizId && (
                              <Button asChild>
                                <Link href={`/dashboard/quizzes?source=${activeCounts.query}&quiz=${activeCounts.quizId}`}>{t('takeQuiz')}</Link>
                              </Button>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                    {sourceDetail?.text_preview && (
                      <details className="border-t border-slate-200 pt-4">
                        <summary className="cursor-pointer text-sm font-medium text-slate-700 hover:text-slate-900">
                          {t('viewText')}
                        </summary>
                        <pre className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-600">
                          {sourceDetail.text_preview}
                          {/* The server sends the opening only, so say so rather than
                              letting the text look like it simply stops. */}
                          {sourceDetail.text_length > sourceDetail.text_preview.length
                            ? `\n\n${t('moreCharacters', {
                                count: (
                                  sourceDetail.text_length - sourceDetail.text_preview.length
                                ).toLocaleString(),
                              })}`
                            : ''}
                        </pre>
                      </details>
                    )}
                  </div>
                )}
              </div>
            </div>
          </section>
        </div>
      </SourceDropZone>
    </div>
  )
}
