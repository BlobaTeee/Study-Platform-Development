'use client'

import { use, useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { Check, ChevronLeft, CircleAlert, Lightbulb, Loader2, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MathText } from '@/components/math-text'
import { PageHeader } from '@/components/page-header'
import { exercisesAPI, type ExerciseDetail } from '@/lib/api'
import { draftSteps, lastGrade, lastHint } from '@/lib/practice'
import { cn } from '@/lib/utils'

/** One practice problem: the prompt, the student's steps, and what the
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

  const back = (
    <Button asChild variant="outline">
      {/* Back to the list, filtered to where this problem came from. */}
      <Link href={exercise ? `/dashboard/practice?notebook=${exercise.notebook_id ?? 'own'}` : '/dashboard/practice'}>
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
    return (
      <div className="mx-auto max-w-3xl space-y-8">
        <PageHeader title={t('title')} action={back} />
        <p className="sheet p-8 text-lg text-slate-700">{t('notFound')}</p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <PageHeader title={t('title')} action={back} />
      <Problem exercise={exercise} />
      {exercise.solution ? (
        <Solved exercise={exercise} />
      ) : (
        <Attempt key={exercise.id} exercise={exercise} onChange={(next) => mutate({ ...data!, data: next }, { revalidate: false })} />
      )}
    </div>
  )
}

function Problem({ exercise }: { exercise: ExerciseDetail }) {
  const t = useTranslations('practice')
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
        <MathText text={exercise.prompt} />
      </p>
      {exercise.origin === 'own' && <p className="mt-3 text-sm text-slate-600">{t('ownGeneralNote')}</p>}
    </section>
  )
}

function Attempt({ exercise, onChange }: { exercise: ExerciseDetail; onChange: (next: ExerciseDetail) => void }) {
  const t = useTranslations('practice')
  // A problem due again comes back with no attempts in its round, so this
  // starts it on an empty page rather than last week's answer.
  const [steps, setSteps] = useState<string[]>(() => draftSteps(exercise.attempts))
  const [busy, setBusy] = useState<'hint' | 'submit' | 'reveal' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const grade = lastGrade(exercise.attempts)
  const hint = lastHint(exercise.attempts)
  const wrongAt = grade?.verdict === 'needs_work' ? grade.first_wrong_step ?? null : null
  const written = steps.filter((s) => s.trim()).length

  const run = async (kind: 'hint' | 'submit' | 'reveal') => {
    if (busy) return
    setBusy(kind)
    setError(null)
    const clean = steps.map((s) => s.trim()).filter(Boolean)
    try {
      const res =
        kind === 'hint' ? await exercisesAPI.hint(exercise.id, clean)
          : kind === 'submit' ? await exercisesAPI.submit(exercise.id, clean)
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
      {grade?.verdict === 'needs_work' && (
        <section className="sheet divide-y divide-slate-200" aria-live="polite" aria-label={t('needsWork', { met: grade.met?.length ?? 0, total: exercise.checkpoint_count })}>
          <div className="p-6 md:p-8">
            <p className="text-lg text-slate-900">
              {t('needsWork', { met: grade.met?.length ?? 0, total: exercise.checkpoint_count })}
            </p>
            <div className="mt-4 flex gap-3">
              <CircleAlert className="mt-1 size-4 shrink-0 text-red-700" aria-hidden />
              <div className="max-w-[65ch] text-base leading-relaxed">
                <p className="text-sm font-medium text-red-800">
                  {wrongAt && wrongAt <= steps.length ? t('wrongAt', { n: wrongAt }) : t('wrongAfterLast')}
                  {grade.error_type ? ` · ${t(`error_${grade.error_type}`)}` : ''}
                </p>
                {grade.detail && <p className="mt-1 text-slate-800"><MathText text={grade.detail} /></p>}
                {grade.hint && (
                  <p className="mt-2 flex gap-2 text-slate-700">
                    <Lightbulb className="mt-1 size-4 shrink-0 text-mode-ink" aria-hidden />
                    <MathText text={grade.hint} />
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
                    <MathText text={c.text} />
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
          {grade?.verdict === 'needs_work' ? t('fixAndResubmit') : t('stepsLead')}
        </p>

        <form
          className="mt-5 space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (written > 0) void run('submit')
          }}
        >
          <ol className="space-y-3">
            {steps.map((step, i) => {
              const flagged = wrongAt === i + 1
              return (
                <li key={i}>
                  <div className="flex items-center justify-between">
                    <label htmlFor={`step-${i}`} className={cn('font-mono text-xs tabular-nums', flagged ? 'text-red-700' : 'text-slate-500')}>
                      {t('step', { n: i + 1 })}
                    </label>
                    {steps.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setSteps((s) => s.filter((_, j) => j !== i))}
                        className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                        aria-label={t('removeStep', { n: i + 1 })}
                      >
                        <X className="size-3.5" aria-hidden />
                      </button>
                    )}
                  </div>
                  <textarea
                    id={`step-${i}`}
                    rows={2}
                    value={step}
                    autoFocus={i === steps.length - 1 && i > 0}
                    onChange={(e) => setSteps((s) => s.map((v, j) => (j === i ? e.target.value : v)))}
                    placeholder={t('stepPlaceholder')}
                    aria-invalid={flagged || undefined}
                    className={cn(
                      'mt-1 block w-full resize-y rounded-lg border bg-white px-4 py-2.5 text-base leading-relaxed text-slate-900 placeholder:text-slate-500 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30',
                      flagged ? 'border-red-400 bg-red-50/40' : 'border-slate-300'
                    )}
                  />
                </li>
              )
            })}
          </ol>

          <Button type="button" variant="ghost" size="sm" onClick={() => setSteps((s) => [...s, ''])} disabled={steps.length >= 20}>
            <Plus aria-hidden />
            {t('addStep')}
          </Button>

          {hint && (
            <p className="flex max-w-[65ch] gap-2 rounded-lg bg-mode/10 px-4 py-3 text-base leading-relaxed text-slate-800" aria-live="polite">
              <Lightbulb className="mt-1 size-4 shrink-0 text-mode-ink" aria-hidden />
              <span>
                <span className="sr-only">{t('hint')}: </span>
                <MathText text={hint} />
              </span>
            </p>
          )}

          <div className="flex flex-wrap items-center justify-end gap-2 pt-2">
            <Button type="button" variant="tinted" onClick={() => void run('hint')} disabled={busy !== null}>
              {busy === 'hint' ? <Loader2 className="animate-spin" aria-hidden /> : <Lightbulb aria-hidden />}
              {busy === 'hint' ? t('hinting') : t('askHint')}
            </Button>
            <Button type="submit" disabled={busy !== null || written === 0}>
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
  const mine = draftSteps(exercise.attempts).filter(Boolean)
  return (
    <section className="sheet divide-y divide-slate-200" aria-live="polite">
      {passed && (
        <div className="p-6 md:p-8">
          <p className="flex items-center gap-2 text-lg text-slate-900">
            <Check className="size-5 text-emerald-700" aria-hidden />
            {t('passed', { count: exercise.checkpoint_count })}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            {exercise.status === 'mastered' ? t('passedFirstTry') : t('passedAfterTries')}
          </p>
        </div>
      )}

      {mine.length > 0 && (
        <Steps title={t('yourSteps')} steps={mine} />
      )}
      <Steps title={t('solution')} steps={exercise.solution ?? []} />

      <div className="p-6 md:p-8">
        <h3 className="text-base font-semibold text-slate-900">{t('checkpoints')}</h3>
        <ul className="mt-3 space-y-1.5">
          {exercise.met_checkpoints.map((c) => (
            <li key={c.id} className="flex max-w-[65ch] gap-2 text-base text-slate-800">
              <Check className="mt-1 size-4 shrink-0 text-emerald-700" aria-hidden />
              <MathText text={c.text} />
            </li>
          ))}
        </ul>
      </div>

      {exercise.mistakes && exercise.mistakes.length > 0 && (
        <div className="p-6 md:p-8">
          <h3 className="text-base font-semibold text-slate-900">{t('commonMistakes')}</h3>
          <ul className="mt-3 space-y-2">
            {exercise.mistakes.map((m, i) => (
              <li key={i} className="max-w-[65ch] text-base text-slate-800">
                <span className="text-sm font-medium text-slate-600">{t(`error_${m.type}`)}: </span>
                <MathText text={m.text} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function Steps({ title, steps }: { title: string; steps: string[] }) {
  const t = useTranslations('practice')
  return (
    <div className="p-6 md:p-8">
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      <ol className="mt-3 space-y-2">
        {steps.map((s, i) => (
          <li key={i} className="flex max-w-[65ch] gap-3 text-base leading-relaxed text-slate-800">
            <span className="mt-0.5 shrink-0 font-mono text-xs tabular-nums text-slate-500">{t('step', { n: i + 1 })}</span>
            <MathText text={s} />
          </li>
        ))}
      </ol>
    </div>
  )
}
