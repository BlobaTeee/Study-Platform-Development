'use client'

import { useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Camera, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { exercisesAPI } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { MAX_FILE_BYTES, fileKind, keyedByFile, kindCounts } from '@/lib/paper'
import { clearDraft, readPaper, renameDraft, usePaperDraft } from '@/lib/paper-draft'

/** A paper the student brings (a photo, a PDF or a Word file), read once and
 *  sat whole, timed and marked out of 10 by its own key. `onStart` gets the
 *  sitting to open. The paper waits here (lib/paper-draft) until it is sat
 *  or put aside, even if the page is left while it is read. */
export function PaperUpload({ onStart }: { onStart: (testId: number) => void }) {
  const t = useTranslations('tests')
  const picker = useRef<HTMLInputElement>(null)
  const owner = String(useAuth().user?.id ?? '')
  const { reading, questions, title, error: readError } = usePaperDraft(owner)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const [dropped, setDropped] = useState<{ id: number; labels: string[] } | null>(null)
  const setTitle = (value: string) => renameDraft(owner, value)
  const shownError = error || (readError
    ? readError.detail ?? (readError.kind === 'noProblem' ? t('paperNoProblem') : t('paperFailed'))
    : '')

  const read = (file: File) => {
    setError('')
    setDropped(null)
    if (!fileKind(file)) return setError(t('paperNotFile'))
    if (file.size > MAX_FILE_BYTES) return setError(t('paperTooLarge'))
    void readPaper(owner, file, file.name.replace(/\.[^.]+$/, ''))
  }

  // Into the sitting: the draft has done its job.
  const open = (id: number) => {
    clearDraft()
    onStart(id)
  }

  const start = async () => {
    setStarting(true)
    setError('')
    try {
      const res = (await exercisesAPI.startPaper(title.trim(), questions)).data
      // Say what was left out before the clock starts; otherwise go straight in.
      if (res.dropped.length) setDropped({ id: res.id, labels: res.dropped })
      else open(res.id)
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      setError(typeof detail === 'string' ? detail : t('paperFailed'))
    } finally {
      setStarting(false)
    }
  }

  const counts = kindCounts(questions)
  const parts = (['choice', 'true_false', 'short', 'written'] as const)
    .filter((k) => counts[k] > 0)
    .map((k) => t(`paperKind_${k}`, { count: counts[k] }))

  return (
    <div className="space-y-4 border-t border-slate-200 pt-8">
      <div>
        <h2 className="font-display text-2xl font-semibold text-slate-900">{t('paperTitle')}</h2>
        <p className="mt-2 text-base leading-relaxed text-slate-500">{t('paperLead')}</p>
      </div>

      <input
        ref={picker}
        type="file"
        accept="image/*,application/pdf,.pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (file) read(file)
        }}
      />

      {questions.length === 0 ? (
        <button
          type="button"
          onClick={() => picker.current?.click()}
          disabled={reading}
          className="flex w-full flex-col items-center gap-3 rounded-xl border-2 border-dashed border-slate-300 bg-white px-6 py-10 text-center transition-colors hover:border-mode hover:bg-mode/5 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 disabled:cursor-wait"
        >
          {reading ? (
            <>
              <Loader2 className="size-8 animate-spin text-mode-ink motion-reduce:animate-none" aria-hidden />
              <span className="text-base font-medium text-slate-900">{t('paperReading')}</span>
              <span className="text-sm text-slate-600">{t('paperReadingHint')}</span>
            </>
          ) : (
            <>
              <span className="grid size-12 place-items-center rounded-full bg-mode/10 text-mode-ink">
                <Camera className="size-6" aria-hidden />
              </span>
              <span className="text-base font-semibold text-slate-900">{t('paperButton')}</span>
              <span className="max-w-[46ch] text-sm leading-relaxed text-slate-600">{t('paperTips')}</span>
            </>
          )}
        </button>
      ) : (
        <Card className="space-y-5 p-6 md:p-8">
          <div className="space-y-2">
            <Label htmlFor="paper-title">{t('paperName')}</Label>
            <Input id="paper-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <p className="text-base text-slate-800">
            {t('paperCount', { count: questions.length })}
            {parts.length > 0 && <span className="text-slate-600"> · {parts.join(' · ')}</span>}
          </p>
          <p className="text-sm text-slate-600">{keyedByFile(questions) ? t('paperKeyFromFile') : t('paperKeySolve')}</p>

          {dropped ? (
            <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm text-amber-900">
                {t('paperDropped', { count: dropped.labels.length, labels: dropped.labels.join(', ') })}
              </p>
              <Button type="button" onClick={() => open(dropped.id)}>{t('paperGo')}</Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <Button type="button" size="lg" disabled={starting || !title.trim()} onClick={() => void start()}>
                {starting ? <Loader2 className="animate-spin" aria-hidden /> : null}
                {starting ? t('paperPreparing') : t('paperStart')}
              </Button>
              <Button type="button" variant="ghost" disabled={starting} onClick={() => picker.current?.click()}>
                {t('paperAnother')}
              </Button>
              <Button type="button" variant="ghost" disabled={starting} onClick={() => { clearDraft(); setDropped(null) }}>
                {t('paperDiscard')}
              </Button>
            </div>
          )}
        </Card>
      )}
      {shownError && <p role="alert" className="text-sm text-red-700">{shownError}</p>}
    </div>
  )
}
