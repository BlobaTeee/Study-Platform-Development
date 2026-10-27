'use client'

import { Suspense, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { ArrowRight, Camera, ChevronDown, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MathText } from '@/components/math-text'
import { PageHeader } from '@/components/page-header'
import { exercisesAPI, type ExerciseSummary, type PhotoQuestion } from '@/lib/api'
import { firstLines, hasMath } from '@/lib/math-text'
import { filtered, filtersFor, inPracticeOrder, parseFilter, type PracticeFilter } from '@/lib/practice'
import { cn } from '@/lib/utils'

/** Must match MIN_OWN_CHARS in backend/exercises/services/problems.py. */
const MIN_CHARS = 15
/** Must match PROBLEM_PHOTO_MAX_BYTES' default in backend/exercises/services/photo.py. */
const MAX_PHOTO_BYTES = 8 * 1024 * 1024

/** Every practice problem in one place, whatever it came from: written from
 *  a notebook's document, or brought by the student. Where it came from is
 *  a filter, not a second place to look. `?notebook=<id>` or `?notebook=own`
 *  opens it filtered, which is how a notebook links here. */
function PracticeList() {
  const t = useTranslations('practice')
  const router = useRouter()
  const searchParams = useSearchParams()
  const filter = parseFilter(searchParams.get('notebook'))
  const { data, isLoading } = useSWR(['/exercises', 'all'], () => exercisesAPI.list({}))
  const all: ExerciseSummary[] = data?.data?.results ?? []
  const filters = filtersFor(all)
  const shown = inPracticeOrder(filtered(all, filter))
  const [writing, setWriting] = useState(filter === 'own')

  const pick = (next: PracticeFilter) => {
    const query = next === 'all' ? '' : `?notebook=${next}`
    router.replace(`/dashboard/practice${query}`, { scroll: false })
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <PageHeader title={t('title')} />

      <OwnProblemForm open={writing} onToggle={() => setWriting((v) => !v)} />

      <section className="sheet p-6 md:p-8" aria-labelledby="practice-list-title">
        <h2 id="practice-list-title" className="sr-only">{t('title')}</h2>
        <p className="max-w-[65ch] text-sm text-slate-600">{t('pageLead')}</p>

        {filters.length > 1 && (
          <div role="group" aria-label={t('filtersLabel')} className="mt-4 flex flex-wrap gap-2">
            <FilterChip active={filter === 'all'} onClick={() => pick('all')} label={t('filterAll')} count={all.length} />
            {filters.map((f) => (
              <FilterChip
                key={f.key}
                active={filter === f.key}
                onClick={() => pick(f.key)}
                label={f.key === 'own' ? t('filterOwn') : f.title}
                count={f.count}
              />
            ))}
          </div>
        )}

        {isLoading ? (
          <div className="mt-4 h-24 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none" aria-busy />
        ) : shown.length === 0 ? (
          <p className="mt-4 max-w-[65ch] text-slate-600">{all.length === 0 ? t('listEmpty') : t('listEmptyFiltered')}</p>
        ) : (
          <ul className="mt-4 divide-y divide-slate-100 border-t border-slate-100">
            {shown.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/dashboard/practice/${p.id}`}
                  className="-mx-2 flex items-center gap-3 rounded-md px-2 py-3 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-base text-slate-900">{p.prompt}</span>
                    <span className="block truncate text-sm text-slate-600">
                      {t(`difficulty_${p.difficulty}`)}
                      {' · '}
                      {p.origin === 'own' ? t('ownSource') : `${p.notebook_title} · ${p.source_title}`}
                    </span>
                  </span>
                  <span
                    className={cn(
                      'shrink-0 text-xs',
                      p.status === 'mastered' ? 'text-emerald-700' : p.due ? 'font-medium text-mode-ink' : 'text-slate-600'
                    )}
                  >
                    {p.due ? t('dueAgain') : p.attempted ? t('status_started') : t(`status_${p.status}`)}
                  </span>
                  <ArrowRight className="size-3.5 shrink-0 text-slate-400" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function FilterChip({ active, onClick, label, count }: { active: boolean; onClick: () => void; label: string; count: number }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30',
        active ? 'border-mode/40 bg-mode/10 text-mode-ink' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
      )}
    >
      {label}
      <span className="font-mono text-xs tabular-nums text-slate-500">{count}</span>
    </button>
  )
}

/** The student's own problem: closed until asked for, since most visits are
 *  to carry on with problems that already exist. */
/** The question as the student will create it, its section's instruction first. */
function asProblem(q: PhotoQuestion) {
  return q.instruction ? `${q.instruction}\n${q.text}` : q.text
}

function OwnProblemForm({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const t = useTranslations('practice')
  const router = useRouter()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reading, setReading] = useState(false)
  const [photo, setPhoto] = useState<string | null>(null)
  // A photo of a whole page gives several questions; the student picks one.
  const [questions, setQuestions] = useState<PhotoQuestion[]>([])
  const [picking, setPicking] = useState(false)
  const picker = useRef<HTMLInputElement>(null)

  useEffect(() => () => {
    if (photo) URL.revokeObjectURL(photo)
  }, [photo])

  // The photo is read into the box, then the student checks it against the
  // thumbnail before creating the problem. Nothing is kept until then.
  const readPhoto = async (file: File) => {
    setError(null)
    if (!file.type.startsWith('image/')) return setError(t('photoNotImage'))
    if (file.size > MAX_PHOTO_BYTES) return setError(t('photoTooLarge'))
    setPhoto(URL.createObjectURL(file))
    setQuestions([])
    setReading(true)
    try {
      const found = (await exercisesAPI.readPhoto(file)).data.questions
      setQuestions(found)
      setPicking(found.length > 1)
      if (found.length === 1) setText(asProblem(found[0]))
    } catch (e) {
      const body = (e as { response?: { data?: { detail?: unknown; no_problem?: boolean } } }).response?.data
      setPhoto(null)
      setError(body?.no_problem ? t('photoNoProblem') : typeof body?.detail === 'string' ? body.detail : t('failed'))
    } finally {
      setReading(false)
    }
  }

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
        <form
          id="own-problem-form"
          className="space-y-4 border-t border-slate-200 p-6 md:p-8"
          onSubmit={(e) => {
            e.preventDefault()
            void create()
          }}
        >
          <label htmlFor="own-problem" className="block max-w-[65ch] text-base leading-relaxed text-slate-700">
            {t('ownLead')}
          </label>
          <div className="flex flex-wrap items-center gap-3">
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
            <Button type="button" variant="outline" onClick={() => picker.current?.click()} disabled={reading || busy}>
              {reading ? <Loader2 className="animate-spin" aria-hidden /> : <Camera aria-hidden />}
              {reading ? t('photoReading') : t('photoButton')}
            </Button>
            <span className="text-sm text-slate-600">{t('photoNote')}</span>
          </div>
          {photo && (
            <div className="flex items-start gap-4" aria-live="polite">
              {/* eslint-disable-next-line @next/next/no-img-element -- a local blob, nothing to optimise */}
              <img src={photo} alt={t('photoAlt')} className="h-24 w-auto max-w-[40%] shrink-0 md:h-40 rounded-md border border-slate-300 object-contain" />
              {!reading && !picking && (
                <div className="max-w-[52ch] space-y-1 text-sm leading-relaxed text-slate-700">
                  <p>{t('photoRead')}</p>
                  {questions.length > 1 && (
                    <button type="button" onClick={() => setPicking(true)} className="font-medium text-mode-ink underline underline-offset-4 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30">
                      {t('photoPickAgain', { count: questions.length })}
                    </button>
                  )}
                </div>
              )}
              {picking && <p className="max-w-[52ch] text-sm leading-relaxed text-slate-700">{t('photoPick', { count: questions.length })}</p>}
            </div>
          )}
          {picking && (
            <ul className="max-h-[26rem] divide-y divide-slate-200 overflow-y-auto rounded-lg border border-slate-300 bg-white">
              {questions.map((q, i) => (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => {
                      setText(asProblem(q))
                      setPicking(false)
                    }}
                    className="flex w-full gap-3 px-4 py-3 text-left hover:bg-slate-50 focus-visible:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-inset focus-visible:ring-mode/30"
                  >
                    <span className="w-20 shrink-0 text-sm font-semibold text-slate-900">{q.label}</span>
                    <span className="line-clamp-2 text-sm leading-relaxed text-slate-700">
                      <MathText text={firstLines(q.text)} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
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
            <Button type="submit" disabled={busy || reading || text.trim().length < MIN_CHARS}>
              {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {busy ? t('ownChecking') : t('ownSubmit')}
            </Button>
          </div>
          {error && <p role="alert" className="max-w-[65ch] text-sm text-red-700">{error}</p>}
        </form>
      )}
    </section>
  )
}

export default function PracticePage() {
  return (
    <Suspense fallback={null}>
      <PracticeList />
    </Suspense>
  )
}
