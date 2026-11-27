'use client'

import { use, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import useSWR, { useSWRConfig } from 'swr'
import { useTranslations } from 'next-intl'
import { Check, ChevronLeft, ChevronRight, CircleAlert, Lightbulb, Loader2, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useConfirm } from '@/components/confirm-dialog'
import { InPageLanguage, useInPageLanguage } from '@/components/in-page-language'
import { PageHeader } from '@/components/page-header'
import { exercisesAPI, type ExerciseDetail } from '@/lib/api'
import { MAX_ANSWER_CHARS, allMarked, describeAnswer, draftText, lastChoice, lastGrade, lastHint, lastMarks, lastSubmitted } from '@/lib/practice'
import { cn } from '@/lib/utils'
import { unplacedFigures } from '@/lib/figures'

/** One practice problem: the prompt, the student's answer (written freely;
 *  the server cuts it into sentences), and what the
 *  grader made of them. The rubric stays on the server until the problem is
 *  solved or the solution is unlocked, so nothing here can give it away. */
export default function PracticePage({ params }: { params: Promise<{ exerciseId: string }> }) {
  const { exerciseId } = use(params)
  const id = Number(exerciseId)
  const t = useTranslations('practice')
  const { data, error: loadError, isLoading, mutate } = useSWR(
    Number.isFinite(id) && id > 0 ? ['/exercises', id] : null,
    () => exercisesAPI.get(id)
  )
  const exercise = data?.data
  const common = useTranslations('common')
  const router = useRouter()
  const { mutate: refresh } = useSWRConfig()
  const [confirm, confirmDialog] = useConfirm()
  const [removing, setRemoving] = useState(false)
  const [removeError, setRemoveError] = useState('')
  const listHref = exercise ? `/dashboard/practice?notebook=${exercise.notebook_id ?? 'own'}` : '/dashboard/practice'

  // A problem the student no longer wants: gone for good, with its attempts,
  // so its mistakes leave the review list too.
  const remove = async () => {
    const ok = await confirm({
      title: t('removeTitle'),
      body: t('removeBody'),
      confirmLabel: t('removeConfirm'),
      cancelLabel: common('cancel'),
    })
    if (!ok) return
    setRemoving(true)
    setRemoveError('')
    try {
      await exercisesAPI.remove(id)
      await Promise.all([refresh(['/exercises', 'all']), refresh(['/exercises/mistakes'])])
      router.push(listHref)
    } catch {
      setRemoveError(t('removeFailed'))
      setRemoving(false)
    }
  }

  const back = (
    <Button asChild variant="outline">
      {/* Back to the list, filtered to where this problem came from. */}
      <Link href={listHref}>
        <ChevronLeft aria-hidden />
        {t('backToList')}
      </Link>
    </Button>
  )

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-8">
        <PageHeader title={t('title')} action={back} />
        <div className="sheet h-72 animate-pulse motion-reduce:animate-none" aria-busy />
      </div>
    )
  }
  if (!exercise || loadError) {
    // "Not found" only when it is not there: a refusal for going too fast
    // or a server error once read as a missing problem (2026-11-25).
    const failed = loadError as { response?: { status?: number; data?: { detail?: unknown } } } | undefined
    const status = failed?.response?.status
    const detail = failed?.response?.data?.detail
    const missing = !loadError || status === 404
    return (
      <div className="mx-auto max-w-3xl space-y-8">
        <PageHeader title={t('title')} action={back} />
        <div className="sheet space-y-4 p-8">
          <p className="text-lg text-slate-700">
            {missing ? t('notFound') : typeof detail === 'string' && detail ? detail : t('loadFailed')}
          </p>
          {!missing && (
            <Button type="button" variant="outline" onClick={() => void mutate()}>{common('retry')}</Button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <PageHeader
        title={t('title')}
        action={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" className="text-slate-500 hover:text-red-700" disabled={removing} onClick={() => void remove()}>
              {removing ? <Loader2 className="animate-spin" aria-hidden /> : <Trash2 aria-hidden />}
              {t('removeProblem')}
            </Button>
            {back}
          </div>
        }
      />
      {removeError && <p role="alert" className="text-sm text-red-700">{removeError}</p>}
      {confirmDialog}
      {exercise.set && <SetNav set={exercise.set} />}
      <Problem exercise={exercise} />
      {exercise.solution ? (
        <Solved exercise={exercise} />
      ) : (
        <Attempt key={exercise.id} exercise={exercise} onChange={(next) => mutate({ ...data!, data: next }, { revalidate: false })} />
      )}
    </div>
  )
}

/** "Question 3 of 8" in a set picked from one photo or file, with the way
 *  to the one before and after, so a whole paper can be worked through. */
function SetNav({ set }: { set: NonNullable<ExerciseDetail['set']> }) {
  const t = useTranslations('practice')
  return (
    <nav aria-label={t('setLabel')} className="flex items-center justify-between gap-3">
      {set.prev_id ? (
        <Button asChild variant="ghost" size="sm">
          <Link href={`/dashboard/practice/${set.prev_id}`}><ChevronLeft aria-hidden />{t('prevInSet')}</Link>
        </Button>
      ) : <span />}
      <p className="font-mono text-sm tabular-nums text-slate-600">{t('setPosition', { index: set.index, total: set.total })}</p>
      {set.next_id ? (
        <Button asChild variant="outline" size="sm">
          <Link href={`/dashboard/practice/${set.next_id}`}>{t('nextInSet')}<ChevronRight aria-hidden /></Link>
        </Button>
      ) : <span />}
    </nav>
  )
}

function Problem({ exercise }: { exercise: ExerciseDetail }) {
  const t = useTranslations('practice')
  const found = useInPageLanguage([exercise.prompt])
  return (
    <section className="sheet p-6 md:p-8" aria-labelledby="problem-title">
      <p className="flex flex-wrap items-center gap-x-2 text-sm text-slate-600">
        <span id="problem-title" className="font-medium text-mode-ink">{t('problem')}</span>
        <span aria-hidden>·</span>
        <span>{t(`difficulty_${exercise.difficulty}`)}</span>
        <span aria-hidden>·</span>
        <span>{exercise.origin === 'own' ? t('ownProblem') : t('fromDocument', { title: exercise.source_title })}</span>
      </p>
      <p className="mt-3 max-w-[65ch] text-lg leading-relaxed text-slate-900 text-pretty">
        <InPageLanguage text={exercise.prompt} found={found} math figures={exercise.figures} />
      </p>
      {unplacedFigures(exercise.prompt, exercise.figures).map((src, i) => (
        // A figure cut from the student's own exam page, as a data URL.
        // eslint-disable-next-line @next/next/no-img-element
        <img key={i} src={src} alt="" className="mt-3 block h-auto max-h-80 max-w-full rounded-md border border-slate-200 bg-white" />
      ))}
      {exercise.origin === 'own' && <p className="mt-3 text-sm text-slate-600">{t('ownGeneralNote')}</p>}
    </section>
  )
}

function Attempt({ exercise, onChange }: { exercise: ExerciseDetail; onChange: (next: ExerciseDetail) => void }) {
  const t = useTranslations('practice')
  // A problem due again comes back with no attempts in its round, so this
  // starts it on an empty box rather than last week's answer.
  const [text, setText] = useState(() => draftText(exercise.attempts))
  const kind = exercise.answer_kind ?? 'written'
  const keyed = kind !== 'written'
  const [choice, setChoice] = useState<string | null>(() => lastChoice(exercise.attempts))
  const [marks, setMarks] = useState<Record<string, boolean>>(() => lastMarks(exercise.attempts))
  const [busy, setBusy] = useState<'hint' | 'submit' | 'reveal' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const grade = lastGrade(exercise.attempts)
  const hint = lastHint(exercise.attempts)
  const wrongAt = grade?.verdict === 'needs_work' ? grade.first_wrong_step ?? null : null
  // The graded sentences, so the flagged one can be quoted while the box is edited.
  const graded = lastSubmitted(exercise.attempts)
  const wrongSentence = wrongAt && wrongAt <= graded.length ? graded[wrongAt - 1] : null
  // Feedback is written in the problem's language; shown in the page's.
  const found = useInPageLanguage([grade?.detail, grade?.hint, hint, ...exercise.met_checkpoints.map((c) => c.text),
    ...exercise.options.map((o) => o.text), ...exercise.statements.map((st) => st.text)])
  const answer = text.trim()
  const tooLong = answer.length > MAX_ANSWER_CHARS
  const ready = kind === 'choice' ? !!choice : kind === 'true_false' ? allMarked(exercise.statements, marks) : !!answer && !tooLong
  const given = kind === 'choice' ? { answer: choice ?? '' }
    : kind === 'true_false' ? { answer: marks } : { text: answer }
  // A keyed miss says only that it missed; the AI's feedback is for written answers.
  const keyedMiss = keyed && grade?.verdict === 'needs_work'

  const run = async (action: 'hint' | 'submit' | 'reveal') => {
    if (busy) return
    setBusy(action)
    setError(null)
    try {
      const res =
        action === 'hint' ? await exercisesAPI.hint(exercise.id, keyed && kind !== 'short' ? describeAnswer(kind, choice, marks) : answer)
          : action === 'submit' ? await exercisesAPI.submit(exercise.id, given)
            : await exercisesAPI.reveal(exercise.id)
      onChange(res.data)
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      setError(typeof detail === 'string' ? detail : t('failed'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      {keyedMiss && (
        <section className="sheet p-6 md:p-8" aria-live="polite">
          <p className="flex items-start gap-2 text-lg text-slate-900">
            <CircleAlert className="mt-1.5 size-4 shrink-0 text-red-700" aria-hidden />
            <span>
              {kind === 'choice' ? t('wrongChoice', { label: grade.answer ?? '' })
                : kind === 'true_false' ? t('tfScore', { correct: grade.correct ?? 0, total: grade.total ?? exercise.statements.length })
                  : t('wrongShort')}
              {' '}<span className="text-slate-600">{t('tryAgainOrHint')}</span>
            </span>
          </p>
        </section>
      )}
      {!keyed && grade?.verdict === 'needs_work' && (
        <section className="sheet divide-y divide-slate-200" aria-live="polite" aria-label={t('needsWork', { met: grade.met?.length ?? 0, total: exercise.checkpoint_count })}>
          <div className="p-6 md:p-8">
            <p className="text-lg text-slate-900">
              {t('needsWork', { met: grade.met?.length ?? 0, total: exercise.checkpoint_count })}
            </p>
            <div className="mt-4 flex gap-3">
              <CircleAlert className="mt-1 size-4 shrink-0 text-red-700" aria-hidden />
              <div className="max-w-[65ch] text-base leading-relaxed">
                <p className="text-sm font-medium text-red-800">
                  {wrongSentence ? t('wrongAtSentence', { n: wrongAt! }) : t('wrongAfterLastSentence')}
                  {grade.error_type ? ` · ${t(`error_${grade.error_type}`)}` : ''}
                </p>
                {wrongSentence && (
                  <blockquote className="mt-2 border-l-2 border-red-300 pl-3 text-slate-700">&ldquo;{wrongSentence}&rdquo;</blockquote>
                )}
                {grade.detail && <p className="mt-2 text-slate-800"><InPageLanguage text={grade.detail} found={found} math /></p>}
                {grade.hint && (
                  <p className="mt-2 flex gap-2 text-slate-700">
                    <Lightbulb className="mt-1 size-4 shrink-0 text-mode-ink" aria-hidden />
                    <InPageLanguage text={grade.hint} found={found} math />
                  </p>
                )}
              </div>
            </div>
          </div>
          {exercise.met_checkpoints.length > 0 && (
            <div className="p-6 md:p-8">
              <h3 className="text-sm font-semibold text-slate-900">{t('reached')}</h3>
              <ul className="mt-2 space-y-1.5">
                {exercise.met_checkpoints.map((c) => (
                  <li key={c.id} className="flex max-w-[65ch] gap-2 text-base text-slate-800">
                    <Check className="mt-1 size-4 shrink-0 text-emerald-700" aria-hidden />
                    <InPageLanguage text={c.text} found={found} math />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <section className="sheet p-6 md:p-8" aria-labelledby="steps-title">
        <h2 id="steps-title" className="text-base font-semibold text-slate-900">{t('yourSteps')}</h2>
        <p className="mt-1 max-w-[65ch] text-sm text-slate-600">
          {kind === 'choice' ? t('choiceLead') : kind === 'true_false' ? t('tfLead') : kind === 'short' ? t('shortLead')
            : grade?.verdict === 'needs_work' ? t('fixSentence') : t('answerLead')}
        </p>

        <form
          className="mt-5 space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (ready) void run('submit')
          }}
        >
          {kind === 'choice' && (
            <ChoiceInput exercise={exercise} value={choice} wrong={keyedMiss ? grade?.answer ?? null : null} onChange={setChoice} found={found} />
          )}
          {kind === 'true_false' && (
            <TrueFalseInput exercise={exercise} marks={marks} onChange={(label, mark) => setMarks((m) => ({ ...m, [label]: mark }))} found={found} />
          )}
          {kind === 'short' && (
            <div className="flex max-w-sm flex-col gap-1.5">
              <label htmlFor="answer" className="text-sm font-medium text-slate-700">{t('shortLabel')}</label>
              <input
                id="answer"
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={160}
                autoComplete="off"
                aria-invalid={keyedMiss ? true : undefined}
                className={cn(
                  'h-11 rounded-lg border bg-white px-4 text-base text-slate-900 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30',
                  keyedMiss ? 'border-red-400' : 'border-slate-300'
                )}
              />
            </div>
          )}
          {!keyed && <label htmlFor="answer" className="sr-only">{t('yourSteps')}</label>}
          {!keyed && <textarea
            id="answer"
            rows={Math.min(14, Math.max(6, text.split('\n').length + 2))}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t('answerPlaceholder')}
            aria-invalid={wrongSentence ? true : undefined}
            aria-describedby={tooLong ? 'answer-too-long' : undefined}
            className={cn(
              'block w-full resize-y rounded-lg border bg-white px-4 py-3 text-base leading-relaxed text-slate-900 placeholder:text-slate-500 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30',
              wrongSentence ? 'border-red-400' : 'border-slate-300'
            )}
          />}
          {!keyed && tooLong && (
            <p id="answer-too-long" role="alert" className="text-sm text-red-700">{t('tooLong', { max: MAX_ANSWER_CHARS })}</p>
          )}

          {hint && (
            <p className="flex max-w-[65ch] gap-2 rounded-lg bg-mode/10 px-4 py-3 text-base leading-relaxed text-slate-800" aria-live="polite">
              <Lightbulb className="mt-1 size-4 shrink-0 text-mode-ink" aria-hidden />
              <span>
                <span className="sr-only">{t('hint')}: </span>
                <InPageLanguage text={hint} found={found} math />
              </span>
            </p>
          )}

          <div className="flex flex-wrap items-center justify-end gap-2 pt-2">
            <Button type="button" variant="tinted" onClick={() => void run('hint')} disabled={busy !== null}>
              {busy === 'hint' ? <Loader2 className="animate-spin" aria-hidden /> : <Lightbulb aria-hidden />}
              {busy === 'hint' ? t('hinting') : t('askHint')}
            </Button>
            <Button type="submit" disabled={busy !== null || !ready}>
              {busy === 'submit' ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {busy === 'submit' ? t('grading') : t('submit')}
            </Button>
          </div>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        </form>
      </section>

      {exercise.can_reveal && (
        <section className="sheet flex flex-wrap items-center justify-between gap-4 p-6 md:p-8">
          <p className="max-w-[48ch] text-base text-slate-700">{t('revealLead', { count: exercise.failed_submits })}</p>
          <Button variant="outline" onClick={() => void run('reveal')} disabled={busy !== null}>
            {busy === 'reveal' ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t('reveal')}
          </Button>
        </section>
      )}
    </>
  )
}

function Solved({ exercise }: { exercise: ExerciseDetail }) {
  const t = useTranslations('practice')
  const grade = lastGrade(exercise.attempts)
  const passed = grade?.verdict === 'passed'
  const keyed = (exercise.answer_kind ?? 'written') !== 'written'
  // The student's own answer, as they wrote it (a choice or marks are shown with the key).
  const mine = exercise.answer_kind === 'choice' || exercise.answer_kind === 'true_false' ? '' : draftText(exercise.attempts)
  const found = useInPageLanguage([
    ...exercise.options.map((o) => o.text),
    ...exercise.statements.map((st) => st.text),
    ...(exercise.solution ?? []),
    ...exercise.met_checkpoints.map((c) => c.text),
    ...(exercise.mistakes ?? []).map((m) => m.text),
  ])
  return (
    <section className="sheet divide-y divide-slate-200" aria-live="polite">
      {passed && (
        <div className="p-6 md:p-8">
          <p className="flex items-center gap-2 text-lg text-slate-900">
            <Check className="size-5 text-emerald-700" aria-hidden />
            {keyed ? t('passedKeyed') : t('passed', { count: exercise.checkpoint_count })}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            {exercise.status === 'mastered' ? t('passedFirstTry') : t('passedAfterTries')}
          </p>
        </div>
      )}

      {mine && (
        <div className="p-6 md:p-8">
          <h3 className="text-base font-semibold text-slate-900">{t('yourSteps')}</h3>
          <p className="mt-3 max-w-[65ch] whitespace-pre-wrap text-base leading-relaxed text-slate-800">{mine}</p>
        </div>
      )}
      {keyed && <KeyAnswer exercise={exercise} found={found} />}
      <Steps title={t('solution')} steps={exercise.solution ?? []} found={found} points={exercise.answer_format === 'points'} />

      {!keyed && <div className="p-6 md:p-8">
        <h3 className="text-base font-semibold text-slate-900">{t('checkpoints')}</h3>
        <ul className="mt-3 space-y-1.5">
          {exercise.met_checkpoints.map((c) => (
            <li key={c.id} className="flex max-w-[65ch] gap-2 text-base text-slate-800">
              <Check className="mt-1 size-4 shrink-0 text-emerald-700" aria-hidden />
              <InPageLanguage text={c.text} found={found} math />
            </li>
          ))}
        </ul>
      </div>}

      {!keyed && exercise.mistakes && exercise.mistakes.length > 0 && (
        <div className="p-6 md:p-8">
          <h3 className="text-base font-semibold text-slate-900">{t('commonMistakes')}</h3>
          <ul className="mt-3 space-y-2">
            {exercise.mistakes.map((m, i) => (
              <li key={i} className="max-w-[65ch] text-base text-slate-800">
                <span className="text-sm font-medium text-slate-600">{t(`error_${m.type}`)}: </span>
                <InPageLanguage text={m.text} found={found} math />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

/** The model solution's numbered steps (or points), with their translation. */
function Steps({ title, steps, found, points = false }: { title: string; steps: string[]; found?: Map<string, string>; points?: boolean }) {
  const t = useTranslations('practice')
  return (
    <div className="p-6 md:p-8">
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      <ol className="mt-3 space-y-2">
        {steps.map((s, i) => (
          <li key={i} className="flex max-w-[65ch] gap-3 text-base leading-relaxed text-slate-800">
            <span className="mt-0.5 shrink-0 font-mono text-xs tabular-nums text-slate-500">{t(points ? 'point' : 'step', { n: i + 1 })}</span>
            <InPageLanguage text={s} found={found} math />
          </li>
        ))}
      </ol>
    </div>
  )
}

/** The options of a choice problem; the one picked last time and found wrong
 *  is marked, so it is not picked again by accident. */
function ChoiceInput({ exercise, value, wrong, onChange, found }: {
  exercise: ExerciseDetail; value: string | null; wrong: string | null
  onChange: (label: string) => void; found?: Map<string, string>
}) {
  const t = useTranslations('practice')
  return (
    <div role="radiogroup" aria-label={t('choiceLead')} className="space-y-2">
      {exercise.options.map((o) => {
        const picked = value === o.label
        const missed = wrong === o.label && picked
        return (
          <button
            key={o.label}
            type="button"
            role="radio"
            aria-checked={picked}
            onClick={() => onChange(o.label)}
            className={cn(
              'flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left text-base leading-relaxed transition-colors',
              'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30',
              missed ? 'border-red-400 bg-red-50' : picked ? 'border-mode bg-mode/10' : 'border-slate-300 bg-white hover:bg-slate-50'
            )}
          >
            <span className={cn('grid size-6 shrink-0 place-items-center rounded-full border text-sm font-medium',
              picked ? 'border-mode bg-mode text-white' : 'border-slate-300 text-slate-700')}>
              {o.label}
            </span>
            <span className="min-w-0 text-slate-900"><InPageLanguage text={o.text} found={found} math /></span>
          </button>
        )
      })}
    </div>
  )
}

/** Each statement with a True / False pair. */
function TrueFalseInput({ exercise, marks, onChange, found }: {
  exercise: ExerciseDetail; marks: Record<string, boolean>
  onChange: (label: string, mark: boolean) => void; found?: Map<string, string>
}) {
  const t = useTranslations('practice')
  return (
    <ul className="divide-y divide-slate-200 rounded-lg border border-slate-300 bg-white">
      {exercise.statements.map((st) => (
        <li key={st.label} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
          <p className="min-w-0 flex-1 text-base leading-relaxed text-slate-900">
            <span className="mr-1.5 font-medium text-slate-600">{st.label})</span>
            <InPageLanguage text={st.text} found={found} math />
          </p>
          <div role="group" aria-label={`${st.label})`} className="flex shrink-0 gap-1.5">
            {[true, false].map((mark) => (
              <button
                key={String(mark)}
                type="button"
                aria-pressed={marks[st.label] === mark}
                onClick={() => onChange(st.label, mark)}
                className={cn(
                  'h-9 min-w-16 rounded-md border px-3 text-sm font-medium transition-colors',
                  'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30',
                  marks[st.label] === mark ? 'border-mode bg-mode text-white' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
                )}
              >
                {mark ? t('markTrue') : t('markFalse')}
              </button>
            ))}
          </div>
        </li>
      ))}
    </ul>
  )
}

/** The key of a solved choice, true/false or short problem, beside what the
 *  student gave. */
function KeyAnswer({ exercise, found }: { exercise: ExerciseDetail; found?: Map<string, string> }) {
  const t = useTranslations('practice')
  const key = exercise.answer_key
  if (!key) return null
  const mine = lastChoice(exercise.attempts)
  const marks = lastMarks(exercise.attempts)
  return (
    <div className="p-6 md:p-8">
      <h3 className="text-base font-semibold text-slate-900">{t('correctAnswer')}</h3>
      {exercise.answer_kind === 'choice' && (
        <ul className="mt-3 space-y-1.5">
          {exercise.options.map((o) => (
            <li key={o.label} className={cn('flex max-w-[65ch] gap-2 text-base',
              o.label === key.answer ? 'font-medium text-emerald-800' : 'text-slate-600')}>
              {o.label === key.answer ? <Check className="mt-1 size-4 shrink-0" aria-hidden /> : <span className="w-4 shrink-0" />}
              <span>{o.label}. <InPageLanguage text={o.text} found={found} math /></span>
              {mine === o.label && mine !== key.answer && <span className="text-sm text-red-700">· {t('yourPick')}</span>}
            </li>
          ))}
        </ul>
      )}
      {exercise.answer_kind === 'true_false' && (
        <ul className="mt-3 space-y-1.5">
          {exercise.statements.map((st) => {
            const right = key.answers?.[st.label]
            return (
              <li key={st.label} className="flex max-w-[65ch] gap-3 text-base text-slate-800">
                <span className={cn('w-12 shrink-0 text-sm font-medium', right ? 'text-emerald-800' : 'text-red-700')}>
                  {right ? t('markTrue') : t('markFalse')}
                </span>
                <span>
                  {st.label}) <InPageLanguage text={st.text} found={found} math />
                  {typeof marks[st.label] === 'boolean' && marks[st.label] !== right && (
                    <span className="ml-1 text-sm text-red-700">· {t('yourPick')}: {marks[st.label] ? t('markTrue') : t('markFalse')}</span>
                  )}
                </span>
              </li>
            )
          })}
        </ul>
      )}
      {exercise.answer_kind === 'short' && (
        <p className="mt-3 text-base text-slate-900"><InPageLanguage text={key.answer ?? ''} found={found} math /></p>
      )}
    </div>
  )
}
