'use client'

import { Suspense, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { ChevronLeft, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/page-header'
import { exercisesAPI, notebooksAPI } from '@/lib/api'

type Notebook = { id: number; title: string }

/** Must match MIN_OWN_CHARS in backend/exercises/services/problems.py. */
const MIN_CHARS = 15

/** The student's own problem: pasted in, checked for being solvable, given
 *  a rubric, then solved on the practice page like any other. */
function OwnProblem() {
  const t = useTranslations('practice')
  const router = useRouter()
  const searchParams = useSearchParams()
  const { data: notebooksRes } = useSWR(['/notebooks/'], () => notebooksAPI.getNotebooks())
  const notebooks: Notebook[] = notebooksRes?.data?.results ?? notebooksRes?.data ?? []
  const [picked, setPicked] = useState<number | null>(null)
  const fromQuery = Number(searchParams.get('notebook'))
  const notebookId = picked ?? (fromQuery > 0 ? fromQuery : notebooks[0]?.id ?? null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const create = async () => {
    if (!notebookId || text.trim().length < MIN_CHARS || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await exercisesAPI.own(notebookId, text.trim())
      router.push(`/dashboard/practice/${res.data.id}`)
    } catch (e) {
      const body = (e as { response?: { data?: { detail?: unknown; incomplete?: boolean } } }).response?.data
      const detail = typeof body?.detail === 'string' ? body.detail : null
      setError(detail ? (body?.incomplete ? t('ownIncomplete', { missing: detail }) : detail) : t('failed'))
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <PageHeader
        title={t('ownTitle')}
        action={
          <Button asChild variant="outline">
            <Link href={notebookId ? `/dashboard/notebooks/${notebookId}` : '/dashboard/notebooks'}>
              <ChevronLeft aria-hidden />
              {t('backToNotebook')}
            </Link>
          </Button>
        }
      />
      <form
        className="sheet space-y-4 p-6 md:p-8"
        onSubmit={(e) => {
          e.preventDefault()
          void create()
        }}
      >
        <label htmlFor="own-problem" className="block max-w-[65ch] text-base leading-relaxed text-slate-700">
          {t('ownLead')}
        </label>
        <textarea
          id="own-problem"
          autoFocus
          rows={7}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t('ownPlaceholder')}
          className="block w-full resize-y rounded-lg border border-slate-300 bg-white px-4 py-3 text-base leading-relaxed text-slate-900 placeholder:text-slate-500 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
        />
        <div className="flex flex-wrap items-end justify-between gap-3">
          {notebooks.length > 1 ? (
            <label className="flex flex-col gap-1 text-sm text-slate-600">
              {t('ownNotebook')}
              <select
                value={notebookId ?? ''}
                onChange={(e) => setPicked(Number(e.target.value))}
                className="h-10 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
              >
                {notebooks.map((n) => (
                  <option key={n.id} value={n.id}>{n.title}</option>
                ))}
              </select>
            </label>
          ) : <span />}
          <Button type="submit" disabled={busy || !notebookId || text.trim().length < MIN_CHARS}>
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {busy ? t('ownChecking') : t('ownSubmit')}
          </Button>
        </div>
        {error && <p role="alert" className="max-w-[65ch] text-sm text-red-700">{error}</p>}
      </form>
    </div>
  )
}

export default function OwnProblemPage() {
  return (
    <Suspense fallback={null}>
      <OwnProblem />
    </Suspense>
  )
}
