'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ArrowLeft, Camera, Check, ChevronDown, Keyboard, Loader2, Maximize2, Pencil, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MathText } from '@/components/math-text'
import { exercisesAPI, type PhotoQuestion } from '@/lib/api'
import { firstLines, hasMath } from '@/lib/math-text'
import { asProblem, photoStep, type PhotoStep } from '@/lib/photo-flow'
import { cn } from '@/lib/utils'

/** Must match MIN_OWN_CHARS in backend/exercises/services/problems.py. */
const MIN_CHARS = 15
/** Must match PROBLEM_PHOTO_MAX_BYTES' default in backend/exercises/services/photo.py. */
const MAX_PHOTO_BYTES = 8 * 1024 * 1024

type Mode = 'photo' | 'type'

/** The student's own problem: closed until asked for, since most visits are
 *  to carry on with problems that already exist. Two ways in, said plainly:
 *  a photo, walked through in three numbered steps, or typing it. */
export function OwnProblemForm({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const t = useTranslations('practice')
  const router = useRouter()
  const [mode, setMode] = useState<Mode>('photo')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const create = async () => {
    if (text.trim().length < MIN_CHARS || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await exercisesAPI.own(text.trim())
      router.push(`/dashboard/practice/${res.data.id}`)
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
          {/* The two ways in, as a choice rather than one long form. */}
          <div role="tablist" aria-label={t('ownToggle')} className="grid grid-cols-2 gap-2 sm:inline-grid sm:w-auto">
            <ModeTab active={mode === 'photo'} onClick={() => setMode('photo')} icon={<Camera aria-hidden />} label={t('modePhoto')} />
            <ModeTab active={mode === 'type'} onClick={() => setMode('type')} icon={<Keyboard aria-hidden />} label={t('modeType')} />
          </div>

          {mode === 'photo' ? (
            <PhotoFlow text={text} setText={setText} busy={busy} onCreate={() => void create()} onError={setError} />
          ) : (
            <TypeFlow text={text} setText={setText} busy={busy} onCreate={() => void create()} />
          )}

          {error && <p role="alert" className="max-w-[65ch] text-sm text-red-700">{error}</p>}
        </div>
      )}
    </section>
  )
}

function ModeTab({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        'inline-flex h-11 items-center justify-center gap-2 rounded-lg border px-5 text-base font-medium transition-colors focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 [&_svg]:size-4',
        active ? 'border-mode bg-mode/10 text-mode-ink' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
      )}
    >
      {icon}
      {label}
    </button>
  )
}

function TypeFlow({ text, setText, busy, onCreate }: {
  text: string
  setText: (v: string) => void
  busy: boolean
  onCreate: () => void
}) {
  const t = useTranslations('practice')
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        onCreate()
      }}
    >
      <label htmlFor="own-problem" className="block max-w-[65ch] text-base leading-relaxed text-slate-700">
        {t('typeLead')}
      </label>
      <textarea
        id="own-problem"
        autoFocus
        rows={6}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t('ownPlaceholder')}
        className="block w-full resize-y rounded-lg border border-slate-300 bg-white px-4 py-3 text-base leading-relaxed text-slate-900 placeholder:text-slate-500 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
      />
      {hasMath(text) && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-sm font-medium text-slate-700">{t('mathPreview')}</p>
          <p className="mt-1 max-w-[65ch] text-base leading-relaxed text-slate-900">
            <MathText text={text} />
          </p>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[48ch] text-sm text-slate-600">{t('ownGeneralNote')}</p>
        <Button type="submit" disabled={busy || text.trim().length < MIN_CHARS}>
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {busy ? t('ownChecking') : t('ownSubmit')}
        </Button>
      </div>
    </form>
  )
}

function PhotoFlow({ text, setText, busy, onCreate, onError }: {
  text: string
  setText: (v: string) => void
  busy: boolean
  onCreate: () => void
  onError: (message: string | null) => void
}) {
  const t = useTranslations('practice')
  const [reading, setReading] = useState(false)
  const [photo, setPhoto] = useState<string | null>(null)
  const [questions, setQuestions] = useState<PhotoQuestion[]>([])
  const [picking, setPicking] = useState(false)
  const [chosen, setChosen] = useState<PhotoQuestion | null>(null)
  const [editing, setEditing] = useState(false)
  const picker = useRef<HTMLInputElement>(null)
  const zoom = useRef<HTMLDialogElement>(null)
  const step = photoStep({ questionCount: questions.length, picking })

  useEffect(() => () => {
    if (photo) URL.revokeObjectURL(photo)
  }, [photo])

  const choose = (q: PhotoQuestion) => {
    setChosen(q)
    setText(asProblem(q))
    setPicking(false)
    setEditing(false)
  }

  // Read once; the photo itself stays in the browser and is never uploaded to be kept.
  const readPhoto = async (file: File) => {
    onError(null)
    if (!file.type.startsWith('image/')) return onError(t('photoNotImage'))
    if (file.size > MAX_PHOTO_BYTES) return onError(t('photoTooLarge'))
    setPhoto(URL.createObjectURL(file))
    setQuestions([])
    setChosen(null)
    setText('')
    setReading(true)
    try {
      const found = (await exercisesAPI.readPhoto(file)).data.questions
      setQuestions(found)
      if (found.length === 1) choose(found[0])
      else setPicking(true)
    } catch (e) {
      const body = (e as { response?: { data?: { detail?: unknown; no_problem?: boolean } } }).response?.data
      setPhoto(null)
      onError(body?.no_problem ? t('photoNoProblem') : typeof body?.detail === 'string' ? body.detail : t('failed'))
    } finally {
      setReading(false)
    }
  }

  const retake = () => {
    setQuestions([])
    setChosen(null)
    setText('')
    setPicking(false)
    picker.current?.click()
  }

  return (
    <div className="space-y-6">
      <Steps current={step} />

      <input
        ref={picker}
        type="file"
        accept="image/*"
        capture="environment"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (file) void readPhoto(file)
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
          <p className="text-base text-slate-800">{t('pickLead', { count: questions.length })}</p>
          <ul className="max-h-[28rem] divide-y divide-slate-200 overflow-y-auto rounded-lg border border-slate-300 bg-white">
            {questions.map((q, i) => (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => choose(q)}
                  className="flex w-full gap-3 px-4 py-3 text-left hover:bg-mode/5 focus-visible:bg-mode/5 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-inset focus-visible:ring-mode/30"
                >
                  <span className="w-24 shrink-0 text-sm font-semibold text-slate-900">{q.label}</span>
                  <span className="line-clamp-2 text-sm leading-relaxed text-slate-700">
                    <MathText text={firstLines(q.text)} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <Button type="button" variant="ghost" size="sm" onClick={retake}>
            <Camera aria-hidden />
            {t('retake')}
          </Button>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">{t('checkTitle')}</h3>
            <p className="mt-1 max-w-[65ch] text-sm leading-relaxed text-slate-700">{t('checkLead')}</p>
          </div>

          {/* The photo and what was read from it, side by side, to compare number by number. */}
          <div className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            {photo && (
              <button
                type="button"
                onClick={() => zoom.current?.showModal()}
                className="group relative overflow-hidden rounded-lg border border-slate-300 bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                aria-label={t('zoomPhoto')}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- a local blob, nothing to optimise */}
                <img src={photo} alt={t('photoAlt')} className="max-h-80 w-full object-contain" />
                <span className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-md bg-slate-900/75 px-2 py-1 text-xs font-medium text-white">
                  <Maximize2 className="size-3.5" aria-hidden />
                  {t('zoomHint')}
                </span>
              </button>
            )}
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              {chosen && <p className="text-sm font-semibold text-mode-ink">{chosen.label}</p>}
              <p className="mt-1 text-base leading-relaxed text-slate-900">
                <MathText text={text} />
              </p>
            </div>
          </div>

          {editing ? (
            <div className="space-y-2">
              <label htmlFor="own-problem-edit" className="block text-sm font-medium text-slate-900">{t('editLabel')}</label>
              <textarea
                id="own-problem-edit"
                autoFocus
                rows={6}
                value={text}
                onChange={(e) => setText(e.target.value)}
                className="block w-full resize-y rounded-lg border border-slate-300 bg-white px-4 py-3 font-mono text-sm leading-relaxed text-slate-900 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
              />
              <p className="text-sm text-slate-600">{t('editHint')}</p>
              <Button type="button" variant="outline" size="sm" onClick={() => setEditing(false)}>
                <Check aria-hidden />
                {t('doneEditing')}
              </Button>
            </div>
          ) : (
            <Button type="button" variant="outline" size="sm" onClick={() => setEditing(true)}>
              <Pencil aria-hidden />
              {t('fixText')}
            </Button>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4">
            {questions.length > 1 ? (
              <Button type="button" variant="ghost" onClick={() => setPicking(true)}>
                <ArrowLeft aria-hidden />
                {t('backToPick')}
              </Button>
            ) : (
              <Button type="button" variant="ghost" onClick={retake}>
                <Camera aria-hidden />
                {t('retake')}
              </Button>
            )}
            <Button type="button" onClick={onCreate} disabled={busy || text.trim().length < MIN_CHARS}>
              {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />}
              {busy ? t('ownChecking') : t('createChecked')}
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
