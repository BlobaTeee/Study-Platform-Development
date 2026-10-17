import type { ExerciseDetail, ExerciseResult } from './api'

type Attempt = Pick<ExerciseDetail['attempts'][number], 'kind' | 'steps' | 'result'>

/** The steps to put in the boxes: whatever was last handed in (a hint or a
 *  submit), so asking for help or a grade never loses what was written. */
export function draftSteps(attempts: Attempt[]): string[] {
  for (let i = attempts.length - 1; i >= 0; i--) {
    if (attempts[i].kind !== 'reveal' && attempts[i].steps.length) return [...attempts[i].steps]
  }
  return ['']
}

export function lastGrade(attempts: Attempt[]): ExerciseResult | null {
  for (let i = attempts.length - 1; i >= 0; i--) {
    if (attempts[i].kind === 'submit') return attempts[i].result
  }
  return null
}

/** The hint asked for since the last submit; a grade brings its own. */
export function lastHint(attempts: Attempt[]): string | null {
  for (let i = attempts.length - 1; i >= 0; i--) {
    if (attempts[i].kind === 'submit') return null
    if (attempts[i].kind === 'hint') return attempts[i].result.hint ?? null
  }
  return null
}

export function toRedo(problems: { status: string; due: boolean }[]): number {
  return problems.filter((p) => p.status === 'revisit' && p.due).length
}
