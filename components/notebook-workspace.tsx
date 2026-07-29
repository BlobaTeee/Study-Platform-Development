'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import useSWR, { mutate } from 'swr'
import { flashcardsAPI, notebooksAPI, quizzesAPI } from '@/lib/api'
import {
  SOURCE_ACCEPT,
  fileTypeLabel,
  flashcardMatchesSourceTag,
  formatSourceIdsForQuery,
  isAllowedSourceFile,
  quizMatchesSourceTag,
  sourceCountLabel,
  titleFromFileName,
} from '@/lib/source-utils'
import { SourceDropZone } from '@/components/source-drop-zone'
import {
  AlertCircle,
  ArrowLeft,
  FileText,
  FileUp,
  HelpCircle,
  Loader2,
  Sparkles,
  Zap,
} from 'lucide-react'
import { cn } from '@/lib/utils'

type SourceItem = {
  id: number
  title: string
  file_type?: 'pdf' | 'docx' | 'pptx'
  original_filename: string
  page_count: number
  status: string
  gemini_summary: string
}

// Shown when the local AI model was unreachable and generation silently
// degraded to the basic fill-in-the-blank pipeline.
const FALLBACK_NOTICE = (kind: string) =>
  `The local AI model was unavailable, so these ${kind} came from the basic ` +
  `fill-in-the-blank fallback (lower quality). Check that Ollama is running ` +
  `— "brew services start ollama" — then generate again.`

export function NotebookWorkspace({ notebookId }: { notebookId: number }) {
  const router = useRouter()
  const [generating, setGenerating] = useState<'flashcards' | 'quiz' | null>(null)
  const [checkedSourceIds, setCheckedSourceIds] = useState<number[]>([])
  const [activeSourceId, setActiveSourceId] = useState<number | null>(null)
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  // Set when generation silently degraded to the extractive fallback, so a
  // lower-quality result is never mistaken for the real generator's output.
  const [warning, setWarning] = useState('')
  const [deletingSourceId, setDeletingSourceId] = useState<number | null>(null)
  const [loadingSource, setLoadingSource] = useState(false)
  const [sourceDetail, setSourceDetail] = useState<{
    extracted_text: string
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

  const { data: flashcardsData } = useSWR(['/flashcards/all'], () =>
    flashcardsAPI.getFlashcards()
  )
  const { data: quizzesData } = useSWR(['/quizzes/all'], () => quizzesAPI.getQuizzes())

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

  // Counted server-side on the exact combined tag, which is the same set
  // generating replaces — so the number shown is always the number a press
  // retires. Counting here instead would use flashcardMatchesSourceTag, whose
  // substring test reports a "source:13" card as belonging to source 1.
  const { data: countsRes } = useSWR(
    generationSourceIds.length > 0
      ? ['/notebooks/material_counts', notebookId, studyQuery]
      : null,
    () => notebooksAPI.getMaterialCounts(notebookId, generationSourceIds)
  )
  const existingCards: number = countsRes?.data?.flashcards ?? 0

  const hasFlashcardsForSources = useMemo(() => {
    if (generationSourceIds.length === 0) return false
    const list = flashcardsData?.data?.results ?? flashcardsData?.data ?? []
    return list.some((f: { tags?: string }) =>
      flashcardMatchesSourceTag(f.tags, generationSourceIds)
    )
  }, [flashcardsData, generationSourceIds])

  const quizForSources = useMemo(() => {
    if (generationSourceIds.length === 0) return null
    const list = quizzesData?.data?.results ?? quizzesData?.data ?? []
    return (
      list.find((q: { description?: string }) =>
        quizMatchesSourceTag(q.description, generationSourceIds)
      ) ?? null
    )
  }, [quizzesData, generationSourceIds])

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
          extracted_text: res.data.extracted_text,
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
      setError('Unsupported file. Use PDF, Word (.docx), or PowerPoint (.pptx).')
      return
    }

    setUploading(true)
    setError('')
    try {
      const res = await notebooksAPI.uploadSource(
        notebookId,
        file,
        uploadTitle || titleFromFileName(file.name)
      )
      setUploadTitle('')
      if (fileRef.current) fileRef.current.value = ''
      setActiveSourceId(res.data.id)
      setCheckedSourceIds((prev) =>
        prev.includes(res.data.id) ? prev : [...prev, res.data.id]
      )
      refresh()
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } }
      setError(ax.response?.data?.detail || 'Upload failed')
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
      setError('Select at least one ready source (checkbox) to generate flashcards.')
      return
    }
    // Generating replaces this selection's deck, so a second press throws away
    // whatever review progress the current cards carry. Cheap to confirm, and
    // impossible to undo from here if we don't.
    if (
      existingCards > 0 &&
      !window.confirm(
        `Replace the ${existingCards} flashcard${existingCards === 1 ? '' : 's'} already made from this selection? ` +
          'The new cards start from scratch, and your review progress on the current ones is retired.'
      )
    ) {
      return
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
        setWarning(FALLBACK_NOTICE('flashcards'))
        return  // stay put so the downgrade is seen, not silently navigated past
      }
      router.push(`/dashboard/flashcards?due=1&source=${studyQuery}`)
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } }
      setError(ax.response?.data?.detail || 'Failed to generate flashcards')
    } finally {
      setGenerating(null)
    }
  }

  const handleGenerateQuiz = async () => {
    if (generationSourceIds.length === 0) {
      setError('Select at least one ready source (checkbox) to generate a quiz.')
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
      if (res.data.generated_by === 'extractive-fallback') {
        setWarning(FALLBACK_NOTICE('quiz questions'))
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
      setError(ax.response?.data?.detail || 'Failed to generate quiz')
    } finally {
      setGenerating(null)
    }
  }

  const canGenerate = generationSourceIds.length > 0

  const handleRemoveSource = async (sourceId: number, title: string) => {
    if (
      !window.confirm(
        `Remove "${title}"? This deletes the file from this notebook. Generated flashcards and quizzes will remain.`
      )
    ) {
      return
    }
    setDeletingSourceId(sourceId)
    setError('')
    try {
      await notebooksAPI.deleteSource(sourceId)
      if (activeSourceId === sourceId) {
        setActiveSourceId(null)
        setSourceDetail(null)
      }
      setCheckedSourceIds((prev) => prev.filter((id) => id !== sourceId))
      mutate(['/flashcards/all'])
      mutate(['/quizzes/all'])
      refresh()
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } }
      setError(ax.response?.data?.detail || 'Failed to remove source')
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
        <p className="text-lg text-slate-500">Notebook not found.</p>
        <Button asChild variant="outline">
          <Link href="/dashboard/notebooks">
            <ArrowLeft className="size-4 mr-2" />
            All notebooks
          </Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      <div className="border-t-[3px] border-mode-library flex items-center justify-between gap-4 px-5 md:px-6 py-4 border-b border-slate-200 shrink-0">
        <div className="min-w-0 flex-1">
          <Link
            href="/dashboard/notebooks"
            className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-mode-library mb-2"
          >
            <ArrowLeft className="size-4" />
            All notebooks
          </Link>
          <h1 className="font-display text-2xl md:text-3xl font-semibold text-slate-900 truncate">
            {notebook.title}
          </h1>
          {notebook.description && (
            <p className="text-base text-slate-500 mt-1 line-clamp-2">
              {notebook.description}
            </p>
          )}
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
        <aside className="w-80 shrink-0 border-r border-slate-200 bg-slate-50 flex flex-col">
          <div className="p-5 border-b border-slate-200 space-y-3">
            <div>
              <h2 className="font-mono text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Sources
              </h2>
              <p className="text-base text-slate-500 mt-1">
                {sources.length} {sources.length === 1 ? 'file' : 'files'}
                {checkedSourceIds.length > 0 && (
                  <span className="text-mode-library"> · {checkedSourceIds.length} selected</span>
                )}
              </p>
            </div>
            {readySources.length > 0 && (
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={selectAllReady}
                  className="text-xs h-8 flex-1"
                >
                  Select all
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={clearChecked}
                  className="text-xs h-8 flex-1"
                >
                  Clear
                </Button>
              </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1 min-h-0">
            {sources.length === 0 ? (
              <div className="m-2 rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center">
                <FileUp className="size-10 text-slate-300 mx-auto mb-3" />
                <p className="text-base text-slate-500 leading-relaxed">
                  Drag a file here or browse below
                </p>
                <p className="text-sm text-slate-500 mt-2">PDF · DOCX · PPTX</p>
              </div>
            ) : (
              sources.map((src) => {
                const isChecked = checkedSourceIds.includes(src.id)
                const isActive = activeSourceId === src.id
                return (
                <div
                  key={src.id}
                  className={cn(
                    'group flex items-stretch gap-0.5 rounded-xl border transition-all duration-200',
                    isActive
                      ? 'bg-mode-library/10 border-mode-library/40'
                      : isChecked
                        ? 'bg-mode-library/5 border-mode-library/20'
                        : 'border-transparent hover:bg-slate-100 hover:border-slate-200'
                  )}
                >
                  <div className="pl-3 py-3 shrink-0 flex items-start">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleSourceCheck(src.id)}
                      title={isChecked ? 'Deselect for generation' : 'Select for generation'}
                      className="mt-1 h-4 w-4 rounded border-slate-300 accent-blue-600"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveSourceId(src.id)}
                    className="flex-1 min-w-0 text-left px-2 py-3"
                  >
                    <div className="flex items-start gap-2">
                      <FileText
                        className={cn(
                          'size-4 shrink-0 mt-0.5',
                          isActive ? 'text-mode-library' : 'text-slate-500'
                        )}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-base font-medium text-slate-900 truncate">{src.title}</p>
                        <p className="text-sm mt-0.5">
                          <span
                            className={
                              src.status === 'ready'
                                ? 'text-emerald-600'
                                : src.status === 'failed'
                                  ? 'text-red-600'
                                  : 'text-amber-600'
                            }
                          >
                            {src.status}
                          </span>
                          <span className="text-slate-500">
                            {' '}
                            · {fileTypeLabel(src.file_type)}
                            {sourceCountLabel(src.file_type, src.page_count)
                              ? ` · ${sourceCountLabel(src.file_type, src.page_count)}`
                              : ''}
                          </span>
                        </p>
                      </div>
                    </div>
                  </button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    title="Remove source"
                    disabled={deletingSourceId === src.id}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleRemoveSource(src.id, src.title)
                    }}
                    className={cn(
                      'shrink-0 my-1.5 mr-1.5 size-9 text-slate-500 hover:text-mode-danger hover:bg-red-50',
                      'opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity',
                      isActive && 'opacity-100'
                    )}
                  >
                    {deletingSourceId === src.id ? (
                      'Removing...'
                    ) : (
                      'Remove'
                    )}
                  </Button>
                </div>
              )})
            )}
          </div>

          <div className="p-3 border-t border-slate-200 space-y-2">
            <Input
              value={uploadTitle}
              onChange={(e) => setUploadTitle(e.target.value)}
              placeholder="Title (optional)"
            />
            <input
              ref={fileRef}
              type="file"
              accept={SOURCE_ACCEPT}
              className="hidden"
              onChange={handleFileInput}
              disabled={uploading}
            />
            <Button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="w-full bg-mode-library hover:bg-mode-library-hover gap-2 h-11 text-base"
            >
              {uploading ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <FileUp className="size-4" />
                  Browse files
                </>
              )}
            </Button>
            <p className="text-xs text-slate-500 text-center leading-snug">
              or drag & drop anywhere here
            </p>
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto p-6 md:p-8">
          {!activeSourceId || !activeListItem ? (
            <div className="h-full flex flex-col justify-center px-4 w-full">
              <div className="w-full rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50 px-8 py-12">
                <FileUp className="size-16 text-slate-300 mx-auto mb-5" />
                <h2 className="text-2xl font-semibold text-slate-900">Add sources to this notebook</h2>
                <p className="text-slate-500 mt-3 text-lg leading-relaxed">
                  Upload files, then check one or more sources to combine them for flashcards and
                  quizzes.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="lg"
                  className="mt-8"
                  onClick={() => fileRef.current?.click()}
                  disabled={uploading}
                >
                  <FileUp className="size-5 mr-2" />
                  Browse files
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
                  <h2 className="text-3xl font-bold text-slate-900 mt-1 truncate">
                    {sourceDetail?.title}
                  </h2>
                  <p className="text-base text-slate-500 mt-2">
                    {activeListItem.original_filename}
                    {sourceCountLabel(activeListItem.file_type, sourceDetail?.page_count ?? 0)
                      ? ` · ${sourceCountLabel(activeListItem.file_type, sourceDetail?.page_count ?? 0)}`
                      : ` · ${fileTypeLabel(activeListItem.file_type)}`}
                  </p>
                </div>
              </div>

              {sourceDetail?.status === 'failed' && sourceDetail.error_message && (
                <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
                  {sourceDetail.error_message}
                </div>
              )}

              {sourceDetail?.gemini_summary && (
                <Card className="border-slate-200 shadow-sheet p-5">
                  <h3 className="font-mono text-xs font-semibold text-mode-library uppercase tracking-wide mb-2 flex items-center gap-1.5">
                    <Sparkles className="size-3.5" />
                    Overview
                  </h3>
                  <p className="text-lg text-slate-600 leading-relaxed">
                    {sourceDetail.gemini_summary}
                  </p>
                </Card>
              )}

              <div>
                <h3 className="text-xl font-semibold text-slate-800 mb-2">
                  Generate study materials
                </h3>
                <p className="text-base text-slate-500 mb-5">
                  {generationSourceIds.length > 1
                    ? `Using ${generationSourceIds.length} selected sources (combined).`
                    : generationSourceIds.length === 1
                      ? 'Using 1 selected source.'
                      : 'Check sources on the left, or open a ready file and generate.'}
                </p>
                {!canGenerate && activeListItem?.status === 'ready' && checkedSourceIds.length === 0 && (
                  <p className="text-base text-amber-600 mb-4">
                    Check this source (checkbox) to include it in generation.
                  </p>
                )}
                <div className="grid sm:grid-cols-2 gap-4">
                  <Card className="border-slate-200 shadow-sheet p-6 h-full transition-shadow hover:shadow-lift">
                    <div className="flex flex-col items-center text-center gap-3">
                      <div className="rounded-xl bg-mode-flashcards/10 p-4">
                        <Zap className="size-8 text-mode-flashcards" />
                      </div>
                      <h4 className="text-xl font-semibold text-slate-900">Flashcards</h4>
                      <p className="text-base text-slate-500">
                        {generationSourceIds.length > 1
                          ? 'From all selected sources'
                          : 'About 10 cards from selection'}
                      </p>
                      {/* Generating replaces this selection's deck rather than
                          adding to it, so saying what is about to be retired
                          matters more than a running total. */}
                      {existingCards > 0 && (
                        <p className="font-mono text-sm text-slate-600 tabular-nums">
                          Replaces {existingCards} card{existingCards === 1 ? '' : 's'}
                        </p>
                      )}
                      <Button
                        onClick={handleGenerateFlashcards}
                        disabled={!canGenerate || generating !== null}
                        size="lg"
                        className="mt-2 bg-mode-flashcards hover:bg-mode-flashcards-hover text-white w-full h-12 text-base"
                      >
                        {generating === 'flashcards' ? (
                          <>
                            <Loader2 className="size-4 animate-spin" />
                            Generating...
                          </>
                        ) : (
                          <>
                            <Sparkles className="size-4" />
                            {existingCards > 0
                              ? 'Regenerate flashcards'
                              : 'Generate flashcards'}
                          </>
                        )}
                      </Button>
                    </div>
                  </Card>

                  <Card className="border-slate-200 shadow-sheet p-6 h-full transition-shadow hover:shadow-lift">
                    <div className="flex flex-col items-center text-center gap-3">
                      <div className="rounded-xl bg-mode-quizzes/10 p-4">
                        <HelpCircle className="size-8 text-mode-quizzes" />
                      </div>
                      <h4 className="text-xl font-semibold text-slate-900">Quiz</h4>
                      <p className="text-base text-slate-500">
                        Multiple-choice from selection
                      </p>
                      <Button
                        onClick={handleGenerateQuiz}
                        disabled={!canGenerate || generating !== null}
                        size="lg"
                        className="mt-2 bg-mode-quizzes hover:bg-mode-quizzes-hover text-white w-full h-12 text-base"
                      >
                        {generating === 'quiz' ? (
                          <>
                            <Loader2 className="size-4 animate-spin" />
                            Generating...
                          </>
                        ) : (
                          <>
                            <Sparkles className="size-4" />
                            Generate quiz
                          </>
                        )}
                      </Button>
                    </div>
                  </Card>
                </div>

                {(hasFlashcardsForSources || quizForSources) && studyQuery && (
                  <div className="flex flex-wrap gap-3 pt-2">
                    {hasFlashcardsForSources && (
                      <Button asChild variant="outline" size="lg" className="h-12 text-base">
                        <Link href={`/dashboard/flashcards?due=1&source=${studyQuery}`}>
                          Study flashcards
                        </Link>
                      </Button>
                    )}
                    {quizForSources && (
                      <Button asChild variant="outline" size="lg" className="h-12 text-base">
                        <Link
                          href={`/dashboard/quizzes?source=${studyQuery}&quiz=${quizForSources.id}`}
                        >
                          Take quiz
                        </Link>
                      </Button>
                    )}
                  </div>
                )}
              </div>

              {sourceDetail?.extracted_text && (
                <details className="rounded-xl border border-slate-200 bg-slate-50">
                  <summary className="px-4 py-3 text-sm text-slate-500 cursor-pointer hover:text-slate-700">
                    View extracted text
                  </summary>
                  <pre className="text-xs text-slate-500 whitespace-pre-wrap max-h-64 overflow-y-auto px-4 pb-4 border-t border-slate-200 pt-3">
                    {sourceDetail.extracted_text.slice(0, 8000)}
                    {sourceDetail.extracted_text.length > 8000 ? '\n\n…' : ''}
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
