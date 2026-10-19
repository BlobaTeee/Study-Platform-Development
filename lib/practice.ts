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

type Listed = {
  id: number; status: string; due: boolean; attempted: boolean
  notebook_id: number | null; notebook_title: string; origin: 'document' | 'own'
}
export type PracticeFilter = 'all' | 'own' | number

/** Next to do first: due again, started, untouched, waiting to come back,
 *  mastered. Newest first within each, so a fresh set is at the top. */
export function inPracticeOrder<T extends Listed>(problems: T[]): T[] {
  const rank = (p: Listed) =>
    p.status === 'revisit' && p.due ? 0
      : p.status === 'new' && p.attempted ? 1
        : p.status === 'new' ? 2
          : p.status === 'revisit' ? 3 : 4
  return [...problems].sort((a, b) => rank(a) - rank(b) || b.id - a.id)
}

export function filtered<T extends Listed>(problems: T[], filter: PracticeFilter): T[] {
  if (filter === 'all') return problems
  if (filter === 'own') return problems.filter((p) => p.origin === 'own')
  return problems.filter((p) => p.notebook_id === filter)
}

/** One filter per notebook that has problems, in order of first appearance,
 *  and one for the student's own problems when there are any. */
export function filtersFor(problems: Listed[]): { key: number | 'own'; title: string; count: number }[] {
  const out = new Map<number | 'own', { key: number | 'own'; title: string; count: number }>()
  for (const p of problems) {
    const key = p.origin === 'own' || p.notebook_id == null ? 'own' : p.notebook_id
    const slot = out.get(key) ?? { key, title: key === 'own' ? '' : p.notebook_title, count: 0 }
    slot.count += 1
    out.set(key, slot)
  }
  const own = out.get('own')
  out.delete('own')
  return [...out.values(), ...(own ? [own] : [])]
}

export function parseFilter(raw: string | null): PracticeFilter {
  if (raw === 'own') return 'own'
  const id = Number(raw)
  return raw && Number.isInteger(id) && id > 0 ? id : 'all'
}
