'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import useSWR, { mutate } from 'swr'
import { notebooksAPI } from '@/lib/api'
import {
  AlertCircle,
  ChevronRight,
  FolderOpen,
  Loader2,
  Plus,
  Trash2,
} from 'lucide-react'

type NotebookItem = {
  id: number
  title: string
  description?: string
  source_count?: number
  sources?: unknown[]
  updated_at: string
}

export default function NotebooksListPage() {
  const router = useRouter()
  const [showCreate, setShowCreate] = useState(false)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [error, setError] = useState('')

  const { data, isLoading, error: loadError } = useSWR(['/notebooks/'], () => notebooksAPI.getNotebooks())
  const notebooks: NotebookItem[] = data?.data?.results ?? data?.data ?? []
  // A failed fetch (backend down / network) must NOT look like an empty list —
  // otherwise a stopped server appears as "your notebooks vanished".
  const unreachable = !!loadError && !data

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
      setError(ax.response?.data?.detail || 'Failed to create notebook')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (e: React.MouseEvent, nb: NotebookItem) => {
    e.preventDefault()
    e.stopPropagation()
    if (
      !window.confirm(
        `Delete "${nb.title}"? Its sources and its flashcards go with it.`
      )
    ) {
      return
    }
    setDeletingId(nb.id)
    setError('')
    try {
      await notebooksAPI.deleteNotebook(nb.id)
      mutate(['/notebooks/'])
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } }
      setError(ax.response?.data?.detail || 'Failed to delete notebook')
    } finally {
      setDeletingId(null)
    }
  }

  const sourceCount = (nb: NotebookItem) =>
    nb.source_count ?? (Array.isArray(nb.sources) ? nb.sources.length : 0)

  return (
    <div className="max-w-4xl mx-auto space-y-8 py-6 md:py-10 px-6 md:px-10">
      <div className="rise border-t-[3px] border-mode-library pt-4 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-library">
            Library
          </p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold text-slate-900 mt-1 text-balance">
            My notebooks
          </h1>
          <p className="text-base text-slate-500 mt-2 leading-relaxed max-w-md text-pretty">
            One notebook per subject. Open one to add sources and turn them into study material.
          </p>
        </div>
        <Button
          onClick={() => setShowCreate(!showCreate)}
          size="lg"
          className="bg-mode-library hover:bg-mode-library-hover shrink-0 h-12"
        >
          <Plus className="size-5 mr-2" />
          New notebook
        </Button>
      </div>

      {error && (
        <div className="flex gap-3 rounded-lg bg-red-50 p-4 border border-red-200">
          <AlertCircle className="size-5 text-mode-danger shrink-0" />
          <p className="text-base text-red-700">{error}</p>
        </div>
      )}

      {showCreate && (
        <Card className="rise border-slate-200 shadow-sheet p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">Create notebook</h2>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="nb-title">Name</Label>
              <Input
                id="nb-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Organic Chemistry, History Essay…"
                required
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="nb-desc">Description (optional)</Label>
              <Input
                id="nb-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What are you studying?"
              />
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="submit" disabled={creating || !title.trim()} className="h-11">
                {creating ? (
                  <>
                    <Loader2 className="size-4 animate-spin mr-2" />
                    Creating…
                  </>
                ) : (
                  'Create & open'
                )}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowCreate(false)}
                className="h-11"
              >
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      {isLoading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="size-10 animate-spin text-mode-library" />
        </div>
      ) : unreachable ? (
        <Card className="border-dashed border-amber-300 bg-amber-50/60 p-12 text-center">
          <AlertCircle className="size-16 text-amber-500 mx-auto mb-4" />
          <p className="text-xl text-amber-950 mb-2">Can&apos;t reach the server</p>
          <p className="text-amber-900/80 mb-6 max-w-md mx-auto">
            Your notebooks are safe — the app just can&apos;t load them right now.
            Make sure the backend is running, then try again.
          </p>
          <Button onClick={() => mutate(['/notebooks/'])} size="lg" variant="outline" className="h-12">
            Retry
          </Button>
        </Card>
      ) : notebooks.length === 0 ? (
        <Card className="border-dashed border-slate-300 p-12 text-center">
          <FolderOpen className="size-16 text-slate-300 mx-auto mb-4" />
          <p className="text-xl text-slate-700 mb-2">No notebooks yet</p>
          <p className="text-slate-500 mb-6">
            Start with one notebook per course or topic, then add your study files inside it.
          </p>
          <Button onClick={() => setShowCreate(true)} size="lg" className="h-12">
            <Plus className="size-5 mr-2" />
            Create your first notebook
          </Button>
        </Card>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {notebooks.map((nb) => (
            <li key={nb.id}>
              <Link href={`/dashboard/notebooks/${nb.id}`} className="block h-full group">
                <Card className="relative overflow-hidden border-slate-200 shadow-sheet p-5 h-full hover:border-mode-library/40 hover:shadow-lift hover:-translate-y-0.5 transition-all duration-200">
                  <span
                    className="absolute left-5 -top-px h-[3px] w-10 rounded-b-full bg-mode-library"
                    aria-hidden
                  />
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <h3 className="text-xl font-semibold text-slate-900 truncate group-hover:text-mode-library transition-colors">
                        {nb.title}
                      </h3>
                      {nb.description && (
                        <p className="text-sm text-slate-500 mt-1 line-clamp-2">
                          {nb.description}
                        </p>
                      )}
                      <p className="font-mono text-xs uppercase tracking-wide text-slate-500 mt-3">
                        {sourceCount(nb)} {sourceCount(nb) === 1 ? 'source' : 'sources'}
                      </p>
                    </div>
                    <ChevronRight className="size-6 text-slate-400 group-hover:text-mode-library shrink-0 transition-colors" />
                  </div>
                  <div className="mt-4 pt-4 border-t border-slate-100 flex justify-end">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={deletingId === nb.id}
                      onClick={(e) => handleDelete(e, nb)}
                      className="text-slate-500 hover:text-mode-danger hover:bg-red-50"
                    >
                      {deletingId === nb.id ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <>
                          <Trash2 className="size-4 mr-1.5" />
                          Delete
                        </>
                      )}
                    </Button>
                  </div>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
