'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ArrowLeft, Camera, Check, ChevronDown, FileText, Loader2, Maximize2, Pencil, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MathText } from '@/components/math-text'
import { exercisesAPI, type PhotoQuestion } from '@/lib/api'
import { firstLines } from '@/lib/math-text'
import { MAX_PICKED, asProblem, fileKind, photoStep, pickAll, togglePick, type PhotoStep } from '@/lib/photo-flow'
import { cn } from '@/lib/utils'

/** Must match MIN_OWN_CHARS in backend/exercises/services/problems.py. */
const MIN_CHARS = 15
/** Must match PROBLEM_PHOTO_MAX_BYTES' default in backend/exercises/services/photo.py. */
const MAX_FILE_BYTES = 15 * 1024 * 1024

/** The student's own problems: closed until asked for, since most visits are
 *  to carry on with problems that already exist. A photo or a file (PDF,
 *  Word), walked through in three numbered steps. */
export function OwnProblemForm({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const t = useTranslations('practice')
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Some of a set could not be made: say which before going to the rest.
  const [partial, setPartial] = useState<{ firstId: number; made: number; skipped: string[] } | null>(null)

  // Problems picked from a photo or file, made together as one set.
  const createSet = async (texts: string[], labels: string[], figures: (string | null)[][]) => {
    if (busy || texts.length === 0) return
    setBusy(true)
    setError(null)
    setPartial(null)
    try {
      const { results, skipped } = (await exercisesAPI.ownSet(texts, figures)).data
      if (skipped.length === 0) return router.push(`/dashboard/practice/${results[0].id}`)
      setPartial({ firstId: results[0].id, made: results.length, skipped: skipped.map((s) => `${labels[s.index] ?? s.index + 1}: ${s.reason}`) })
      setBusy(false)
    } catch (e) {
      const body = (e as { response?: { data?: { detail?: unknown; incomplete?: boolean } } }).response?.data
      const detail = typeof body?.detail === 'string' ? body.detail : null
      setError(detail ? (body?.incomplete ? t('ownIncomplete', { missing: detail }) : detail) : t('failed'))
      setBusy(false)
    }
  }

  return (
    <section className="sheet">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls="own-problem-form"
        className="flex w-full items-center gap-2 rounded-xl px-6 py-4 text-left text-base font-medium text-slate-900 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 md:px-8"
      >
        <ChevronDown
          className={cn('size-4 text-slate-500 transition-transform duration-200 motion-reduce:transition-none', !open && '-rotate-90')}
          aria-hidden
        />
        {t('ownToggle')}
      </button>
      {open && (
        <div id="own-problem-form" className="space-y-6 border-t border-slate-200 p-6 md:p-8">
          <PhotoFlow busy={busy} onCreate={(texts, labels, figures) => void createSet(texts, labels, figures)} onError={setError} />

          {error && <p role="alert" className="max-w-[65ch] text-sm text-red-700">{error}</p>}
          {partial && (
            <div role="status" className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
              <p className="text-base text-slate-900">{t('skippedLead', { made: partial.made, count: partial.skipped.length })}</p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                {partial.skipped.map((reason, i) => <li key={i}>{reason}</li>)}
              </ul>
              <Button type="button" size="sm" onClick={() => router.push(`/dashboard/practice/${partial.firstId}`)}>
                {t('startSet')}
              </Button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function PhotoFlow({ busy, onCreate, onError }: {
  busy: boolean
  onCreate: (texts: string[], labels: string[], figures: (string | null)[][]) => void
  onError: (message: string | null) => void
}) {
  const t = useTranslations('practice')
  const [reading, setReading] = useState(false)
  const [photo, setPhoto] = useState<string | null>(null)
  const [fileName, setFileName] = useState('')
  const [questions, setQuestions] = useState<PhotoQuestion[]>([])
  const [picked, setPicked] = useState<number[]>([])
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [picking, setPicking] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const picker = useRef<HTMLInputElement>(null)
  const zoom = useRef<HTMLDialogElement>(null)
  const step = photoStep({ questionCount: questions.length, picking })
  const texts = picked.map((i) => (drafts[i] ?? asProblem(questions[i])).trim())
  const ready = texts.length > 0 && texts.every((x) => x.length >= MIN_CHARS)

  useEffect(() => () => {
    if (photo) URL.revokeObjectURL(photo)
  }, [photo])

  const check = (indexes: number[]) => {
    setPicked(indexes)
    setPicking(false)
    setEditing(null)
  }

  // Read once; the file stays in the browser and is never kept on the server.
  const readFile = async (file: File) => {
    onError(null)
    const kind = fileKind(file)
    if (!kind) return onError(t('photoNotImage'))
    if (file.size > MAX_FILE_BYTES) return onError(t('photoTooLarge'))
    setPhoto(kind === 'image' ? URL.createObjectURL(file) : null)
    setFileName(file.name)
    setQuestions([])
    setPicked([])
    setDrafts({})
    setReading(true)
    try {
      const found = (await exercisesAPI.readPhoto(file)).data.questions
      setQuestions(found)
      if (found.length === 1) check([0])
      else setPicking(true)
    } catch (e) {
      const body = (e as { response?: { data?: { detail?: unknown; no_problem?: boolean } } }).response?.data
      setPhoto(null)
      setFileName('')
      onError(body?.no_problem ? t('photoNoProblem') : typeof body?.detail === 'string' ? body.detail : t('failed'))
    } finally {
      setReading(false)
    }
  }

  const another = () => {
    setQuestions([])
    setPicked([])
    setDrafts({})
    setPicking(false)
    picker.current?.click()
  }

  return (
    <div className="space-y-6">
      <Steps current={step} />

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
          if (file) void readFile(file)
        }}
      />

      {step === 1 && (
        <button
          type="button"
          onClick={() => picker.current?.click()}
          disabled={reading}
          className="flex w-full flex-col items-center gap-3 rounded-xl border-2 border-dashed border-slate-300 bg-slate-50/60 px-6 py-10 text-center transition-colors hover:border-mode hover:bg-mode/5 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 disabled:cursor-wait"
        >
          {reading ? (
            <>
              <Loader2 className="size-8 animate-spin text-mode-ink motion-reduce:animate-none" aria-hidden />
              <span className="text-base font-medium text-slate-900">{t('photoReading')}</span>
              <span className="text-sm text-slate-600">{t('photoReadingHint')}</span>
            </>
          ) : (
            <>
              <span className="grid size-12 place-items-center rounded-full bg-mode/10 text-mode-ink">
                <Camera className="size-6" aria-hidden />
              </span>
              <span className="text-base font-semibold text-slate-900">{t('photoButton')}</span>
              <span className="max-w-[46ch] text-sm leading-relaxed text-slate-600">{t('photoTips')}</span>
            </>
          )}
        </button>
      )}

      {step === 2 && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-base text-slate-800">{t('pickLead', { count: questions.length, max: MAX_PICKED })}</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setPicked(picked.length ? [] : pickAll(questions.length))}
            >
              {picked.length ? t('pickNone') : t('pickAll')}
            </Button>
          </div>
          <ul className="max-h-[28rem] divide-y divide-slate-200 overflow-y-auto rounded-lg border border-slate-300 bg-white">
            {questions.map((q, i) => {
              const on = picked.includes(i)
              const full = !on && picked.length >= MAX_PICKED
              return (
                <li key={i}>
                  <label
                    className={cn(
                      'flex cursor-pointer gap-3 px-4 py-3 hover:bg-mode/5 has-[:focus-visible]:bg-mode/5',
                      full && 'cursor-not-allowed opacity-50'
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={on}
                      disabled={full}
                      onChange={() => setPicked((p) => togglePick(p, i))}
                      className="mt-0.5 size-4 shrink-0 accent-mode-strong"
                    />
                    <span className="w-20 shrink-0 text-sm font-semibold text-slate-900">{q.label}</span>
                    <span className="line-clamp-2 text-sm leading-relaxed text-slate-700">
                      <MathText text={firstLines(q.text)} />
                    </span>
                  </label>
                </li>
              )
            })}
          </ul>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button type="button" variant="ghost" size="sm" onClick={another}>
              <Camera aria-hidden />
              {t('retake')}
            </Button>
            <Button type="button" onClick={() => check(picked)} disabled={picked.length === 0}>
              {t('pickContinue', { count: picked.length })}
            </Button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">{t('checkTitle')}</h3>
            <p className="mt-1 max-w-[65ch] text-sm leading-relaxed text-slate-700">{t('checkLead')}</p>
          </div>

          {photo ? (
            <button
              type="button"
              onClick={() => zoom.current?.showModal()}
              className="group relative block max-w-md overflow-hidden rounded-lg border border-slate-300 bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
              aria-label={t('zoomPhoto')}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- a local blob, nothing to optimise */}
              <img src={photo} alt={t('photoAlt')} className="max-h-64 w-full object-contain" />
              <span className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-md bg-slate-900/75 px-2 py-1 text-xs font-medium text-white">
                <Maximize2 className="size-3.5" aria-hidden />
                {t('zoomHint')}
              </span>
            </button>
          ) : (
            fileName && <p className="inline-flex items-center gap-2 rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-700"><FileText className="size-4" aria-hidden />{fileName}</p>
          )}

          <ol className="space-y-3">
            {picked.map((i) => {
              const text = drafts[i] ?? asProblem(questions[i])
              return (
                <li key={i} className="rounded-lg border border-slate-200 bg-white px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-mode-ink">{questions[i].label}</p>
                    <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(editing === i ? null : i)}>
                      {editing === i ? <Check aria-hidden /> : <Pencil aria-hidden />}
                      {editing === i ? t('doneEditing') : t('fixText')}
                    </Button>
                  </div>
                  <p className="mt-1 text-base leading-relaxed text-slate-900"><MathText text={text} figures={questions[i].figures} /></p>
                  {editing === i && (
                    <div className="mt-3 space-y-2">
                      <label htmlFor={`own-problem-edit-${i}`} className="block text-sm font-medium text-slate-900">{t('editLabel')}</label>
                      <textarea
                        id={`own-problem-edit-${i}`}
                        autoFocus
                        rows={6}
                        value={text}
                        onChange={(e) => setDrafts((d) => ({ ...d, [i]: e.target.value }))}
                        className="block w-full resize-y rounded-lg border border-slate-300 bg-white px-4 py-3 font-mono text-sm leading-relaxed text-slate-900 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                      />
                      <p className="text-sm text-slate-600">{t('editHint')}</p>
                    </div>
                  )}
                </li>
              )
            })}
          </ol>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4">
            {questions.length > 1 ? (
              <Button type="button" variant="ghost" onClick={() => setPicking(true)}>
                <ArrowLeft aria-hidden />
                {t('backToPick')}
              </Button>
            ) : (
              <Button type="button" variant="ghost" onClick={another}>
                <Camera aria-hidden />
                {t('retake')}
              </Button>
            )}
            <Button type="button" onClick={() => onCreate(texts, picked.map((i) => questions[i].label), picked.map((i) => questions[i].figures ?? []))} disabled={busy || !ready}>
              {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />}
              {busy ? t('creatingSet') : texts.length > 1 ? t('createSet', { count: texts.length }) : t('createChecked')}
            </Button>
          </div>
          <p className="max-w-[65ch] text-sm text-slate-600">{t('ownGeneralNote')}</p>

          {photo && (
            <dialog
              ref={zoom}
              onClick={(e) => {
                if (e.target === e.currentTarget) e.currentTarget.close()
              }}
              className="m-auto max-h-[92vh] max-w-[92vw] rounded-xl bg-white p-0 backdrop:bg-slate-900/70"
              aria-label={t('photoAlt')}
            >
              <div className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element -- a local blob, nothing to optimise */}
                <img src={photo} alt={t('photoAlt')} className="max-h-[92vh] max-w-[92vw] object-contain" />
                <button
                  type="button"
                  onClick={() => zoom.current?.close()}
                  aria-label={t('zoomClose')}
                  className="absolute right-3 top-3 grid size-10 place-items-center rounded-full bg-slate-900/75 text-white hover:bg-slate-900 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-white/60"
                >
                  <X className="size-5" aria-hidden />
                </button>
              </div>
            </dialog>
          )}
        </div>
      )}
    </div>
  )
}

/** ① Take the photo ─ ② Choose a question ─ ③ Check: where the student is. */
function Steps({ current }: { current: PhotoStep }) {
  const t = useTranslations('practice')
  const names = [t('step1'), t('step2'), t('step3')]
  return (
    <ol className="flex items-center gap-2 text-sm" aria-label={t('stepsLabel')}>
      {names.map((name, i) => {
        const n = (i + 1) as PhotoStep
        const done = n < current
        const here = n === current
        return (
          <li key={name} className="flex min-w-0 items-center gap-2" aria-current={here ? 'step' : undefined}>
            {i > 0 && <span className={cn('h-px w-4 shrink-0 sm:w-8', done || here ? 'bg-mode' : 'bg-slate-300')} aria-hidden />}
            <span
              className={cn(
                'grid size-6 shrink-0 place-items-center rounded-full font-mono text-xs font-semibold',
                here ? 'bg-mode-strong text-mode-on' : done ? 'bg-mode/15 text-mode-ink' : 'bg-slate-100 text-slate-600'
              )}
            >
              {done ? <Check className="size-3.5" aria-hidden /> : n}
            </span>
            <span className={cn('truncate', here ? 'font-semibold text-slate-900' : 'text-slate-600')}>{name}</span>
          </li>
        )
      })}
    </ol>
  )
}
