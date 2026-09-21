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
  sourceCountLabel,
  titleFromFileName,
} from '@/lib/source-utils'
import { SourceDropZone } from '@/components/source-drop-zone'
import { useConfirm } from '@/components/confirm-dialog'
import {
  AlertCircle,
  ArrowLeft,
  ClipboardPaste,
  Link2,
  FileUp,
  HelpCircle,
  Loader2,
  Zap,
  Download,
  Pencil,
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


export function NotebookWorkspace({ notebookId }: { notebookId: number }) {
  const router = useRouter()
  const t = useTranslations('notebooks')
  const common = useTranslations('common')
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

  const generationSourceIds = useMemo(() => {
    const readyChecked = checkedSourceIds.filter((id) => {
      const s = sources.find((x) => x.id === id)
      return s?.status === 'ready'
    })
    if (readyChecked.length > 0) return readyChecked
    if (activeSourceId) {
      const s = sources.find((x) => x.id === activeSourceId)
      if (s?.status === 'ready') return [activeSourceId]
    }
    return []
  }, [checkedSourceIds, activeSourceId, sources])

  const studyQuery = formatSourceIdsForQuery(generationSourceIds)

  // Counted server-side as the exact source set, which is the same set
  // generating replaces — so the number shown is always the number a press
  // retires. The page has no card list to count from anyway.
  const { data: countsRes } = useSWR(
    generationSourceIds.length > 0
      ? ['/notebooks/material_counts', notebookId, studyQuery]
      : null,
    () => notebooksAPI.getMaterialCounts(notebookId, generationSourceIds)
  )
  const existingCards: number = countsRes?.data?.flashcards ?? 0
  // Both of these used to be derived by downloading every flashcard and every
  // quiz the user owns and scanning for a tag match — a cost that grew with
  // the whole collection to answer a question about one selection. The server
  // answers it directly now, and more accurately: its tag comparison is exact,
  // where the client matchers' substring test reads a "source:13" card as
  // belonging to source 1.
  const hasFlashcardsForSources = existingCards > 0
  const quizIdForSources: number | null = countsRes?.data?.quiz_id ?? null

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
      setCheckedSourceIds((prev) =>
        prev.includes(res.data.id) ? prev : [...prev, res.data.id]
      )
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
      setCheckedSourceIds((prev) => (prev.includes(res.data.id) ? prev : [...prev, res.data.id]))
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

  const handleGenerateFlashcards = async () => {
    if (generationSourceIds.length === 0) {
      setError(t('selectToGenerateFlashcards'))
      return
    }
    // Generating replaces this selection's deck, so a second press throws away
    // whatever review progress the current cards carry. Cheap to confirm, and
    // impossible to undo from here if we don't.
    if (existingCards > 0) {
      const ok = await confirm({
        title: t('replaceTitle', { cards: common('cards', { count: existingCards }) }),
        body: t('replaceBody'),
        confirmLabel: t('replaceConfirm'),
      })
      if (!ok) return
    }
    setGenerating('flashcards')
    setError('')
    setWarning('')
    try {
      const res = await notebooksAPI.generateFlashcardsFromSources(
        notebookId,
        generationSourceIds
      )
      mutate(['/flashcards/'])
      // The deck this selection holds just changed. Matters on the fallback
      // branch below, which stays on this page — without it the card the
      // button offers to replace is the one it replaced a moment ago.
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

  const handleGenerateQuiz = async () => {
    if (generationSourceIds.length === 0) {
      setError(t('selectToGenerateQuiz'))
      return
    }
    setGenerating('quiz')
    setError('')
    setWarning('')
    try {
      const res = await notebooksAPI.generateQuizFromSources(
        notebookId,
        generationSourceIds
      )
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

  const canGenerate = generationSourceIds.length > 0

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
      // The removed source drops out of the selection, so the counts keyed on
      // the old selection no longer describe anything on screen.
      mutate(['/notebooks/material_counts', notebookId, studyQuery])
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
        <div className="flex basis-full items-center gap-1 text-sm text-slate-600 sm:basis-auto">
          <Download className="size-4" aria-hidden />
          <span className="mr-1">{t('export')}</span>
          <Button type="button" variant="ghost" size="sm" disabled={exporting !== null} onClick={() => void exportCsv('flashcards')}>
            {t('exportCards')}
          </Button>
          <Button type="button" variant="ghost" size="sm" disabled={exporting !== null} onClick={() => void exportCsv('questions')}>
            {t('exportQuestions')}
          </Button>
        </div>
      </div>

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

      <SourceDropZone onFile={uploadFile} disabled={!canDrop} className="flex flex-1 min-h-0">
        <aside className="flex w-72 shrink-0 flex-col border-r border-slate-200 bg-slate-50">
          <div className="flex items-baseline justify-between gap-3 border-b border-slate-200 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">
              {t('sources')}
              <span className="ml-1.5 font-mono text-xs font-normal text-slate-600 tabular-nums">{sources.length}</span>
              {checkedSourceIds.length > 0 && (
                <span className="ml-1.5 text-xs font-normal text-mode">{t('selectedCount', { count: checkedSourceIds.length })}</span>
              )}
            </h2>
            {readySources.length > 0 && (
              <button
                type="button"
                onClick={checkedSourceIds.length === readySources.length ? clearChecked : selectAllReady}
                className="text-sm font-medium text-mode hover:underline"
              >
                {checkedSourceIds.length === readySources.length ? t('clear') : t('selectAll')}
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1 min-h-0">
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
                  <div className="pl-3 py-3 shrink-0 flex items-start">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleSourceCheck(src.id)}
                      title={isChecked ? t('deselectForGeneration') : t('selectForGeneration')}
                      className="mt-1 size-4 rounded border-slate-300 accent-[var(--mode)]"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveSourceId(src.id)}
                    className="min-w-0 flex-1 px-2 py-2.5 text-left"
                  >
                    <p className={cn('truncate text-[15px] font-medium', isActive ? 'text-slate-900' : 'text-slate-800')}>{src.title}</p>
                    <p className="mt-0.5 text-sm text-slate-600">
                      {src.status === 'failed' ? (
                        <span className="text-red-700">{t('statusFailed')}</span>
                      ) : src.status !== 'ready' ? (
                        <span className="text-amber-700">{t('statusProcessing')}</span>
                      ) : (
                        <>
                          {src.file_type === 'text' ? t('typeText') : src.file_type === 'url' ? t('typeLink') : fileTypeLabel(src.file_type)}
                          {sourceCountLabel(src.file_type, src.page_count) ? `, ${sourceCountLabel(src.file_type, src.page_count)}` : ''}
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
                    {deletingSourceId === src.id ? (
                      t('removing')
                    ) : (
                      t('remove')
                    )}
                  </Button>
                </div>
              )})
            )}
          </div>

          <div className="space-y-2 border-t border-slate-200 p-3">
            <input
              ref={fileRef}
              type="file"
              accept={SOURCE_ACCEPT}
              className="hidden"
              onChange={handleFileInput}
              disabled={uploading}
            />
            <Button onClick={() => fileRef.current?.click()} disabled={uploading} className="w-full">
              {uploading ? (
                <>
                  <Loader2 className="animate-spin" aria-hidden />
                  {t('processing')}
                </>
              ) : (
                <>
                  <FileUp aria-hidden />
                  {t('browseFiles')}
                </>
              )}
            </Button>
            <div className="grid grid-cols-2 gap-2">
              <Button
                type="button"
                variant={composer === 'text' ? 'tinted' : 'outline'}
                size="sm"
                aria-pressed={composer === 'text'}
                onClick={() => setComposer(composer === 'text' ? null : 'text')}
              >
                <ClipboardPaste aria-hidden />
                {t('pasteText')}
              </Button>
              <Button
                type="button"
                variant={composer === 'url' ? 'tinted' : 'outline'}
                size="sm"
                aria-pressed={composer === 'url'}
                onClick={() => setComposer(composer === 'url' ? null : 'url')}
              >
                <Link2 aria-hidden />
                {t('addLink')}
              </Button>
            </div>
            <p className="text-center text-xs text-slate-500">{t('orDrop')}</p>
            {composer && (
              <form
                className="space-y-2 pt-1"
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
                <Button type="submit" disabled={uploading || !composerBody.trim()} className="w-full">
                  {uploading ? t('adding') : t('addSource')}
                </Button>
              </form>
            )}
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto p-6 md:p-10">
          {!activeSourceId || !activeListItem ? (
            <div className="flex h-full w-full flex-col justify-center">
              <div className="max-w-[48ch]">
                <h2 className="font-display text-2xl font-semibold text-slate-900">{t('addSourcesTitle')}</h2>
                <p className="mt-3 text-base leading-relaxed text-slate-600">{t('addSourcesBody')}</p>
                <Button type="button" size="lg" className="mt-6" onClick={() => fileRef.current?.click()} disabled={uploading}>
                  <FileUp aria-hidden />
                  {t('browseFiles')}
                </Button>
              </div>
            </div>
          ) : loadingSource ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 className="size-8 animate-spin text-mode-library" />
            </div>
          ) : (
            <div className="w-full space-y-6">
              <div className="flex items-start justify-between gap-4">
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
                        className="text-mode-library hover:underline break-all"
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
                        : sourceCountLabel(activeListItem.file_type, sourceDetail?.page_count ?? 0)
                          ? `, ${activeListItem.file_type === 'pptx' ? t('slides', { count: sourceDetail?.page_count ?? 0 }) : t('pages', { count: sourceDetail?.page_count ?? 0 })}`
                          : `, ${fileTypeLabel(activeListItem.file_type)}`}
                  </p>
                </div>
              </div>

              {sourceDetail?.status === 'failed' && sourceDetail.error_message && (
                <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
                  {sourceDetail.error_message}
                </div>
              )}

              {sourceDetail?.gemini_summary && (
                <div className="border-t border-slate-200 pt-5">
                  <h3 className="text-sm font-semibold text-slate-900">{t('overview')}</h3>
                  <p className="mt-2 max-w-[65ch] text-base leading-relaxed text-slate-700">{sourceDetail.gemini_summary}</p>
                </div>
              )}

              <div className="border-t border-slate-200 pt-5">
                <h3 className="text-sm font-semibold text-slate-900">{t('generateTitle')}</h3>
                <p className="mt-1 text-sm text-slate-600">
                  {generationSourceIds.length > 1
                    ? t('usingSelected', { count: generationSourceIds.length })
                    : generationSourceIds.length === 1
                      ? t('usingOne')
                      : t('checkToGenerate')}
                </p>
                {!canGenerate && activeListItem?.status === 'ready' && checkedSourceIds.length === 0 && (
                  <p className="mt-2 text-sm text-amber-700">{t('checkThisSource')}</p>
                )}

                {/* Two things you can make, each in its own colour: a row per
                    kind, the action on the right, no tiles. */}
                <div className="mt-4 divide-y divide-slate-200 rounded-xl border border-slate-200">
                  <div data-mode="flashcards" className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 p-4">
                    <div className="min-w-0 flex-1 basis-56">
                      <p className="flex items-center gap-2 text-base font-semibold text-slate-900">
                        <Zap className="size-4 text-mode" aria-hidden />
                        Flashcards
                      </p>
                      <p className="mt-0.5 text-sm text-slate-600">
                        {generationSourceIds.length > 1 ? t('fromAllSelected') : t('aboutTenCards')}
                        {existingCards > 0 && (
                          <span className="block text-slate-600">{t('replacesCards', { cards: common('cards', { count: existingCards }) })}</span>
                        )}
                      </p>
                    </div>
                    <Button onClick={handleGenerateFlashcards} disabled={!canGenerate || generating !== null} className="shrink-0">
                      {generating === 'flashcards' ? (
                        <>
                          <Loader2 className="animate-spin" aria-hidden />
                          {t('generating')}
                        </>
                      ) : existingCards > 0 ? t('regenerateFlashcards') : t('generateFlashcards')}
                    </Button>
                  </div>
                  <div data-mode="quizzes" className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 p-4">
                    <div className="min-w-0 flex-1 basis-56">
                      <p className="flex items-center gap-2 text-base font-semibold text-slate-900">
                        <HelpCircle className="size-4 text-mode" aria-hidden />
                        Quiz
                      </p>
                      <p className="mt-0.5 text-sm text-slate-600">{t('multipleChoice')}</p>
                    </div>
                    <Button onClick={handleGenerateQuiz} disabled={!canGenerate || generating !== null} className="shrink-0">
                      {generating === 'quiz' ? (
                        <>
                          <Loader2 className="animate-spin" aria-hidden />
                          {t('generating')}
                        </>
                      ) : t('generateQuiz')}
                    </Button>
                  </div>
                </div>

                {(hasFlashcardsForSources || quizIdForSources) && studyQuery && (
                  <div className="mt-4 flex flex-wrap gap-3">
                    {hasFlashcardsForSources && (
                      <Button asChild variant="tinted" data-mode="flashcards">
                        <Link href={`/dashboard/flashcards?due=1&source=${studyQuery}`}>{t('studyFlashcards')}</Link>
                      </Button>
                    )}
                    {quizIdForSources && (
                      <Button asChild variant="tinted" data-mode="quizzes">
                        <Link href={`/dashboard/quizzes?source=${studyQuery}&quiz=${quizIdForSources}`}>{t('takeQuiz')}</Link>
                      </Button>
                    )}
                  </div>
                )}
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
        </main>
      </SourceDropZone>
    </div>
  )
}
