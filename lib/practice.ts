import type { ExerciseDetail, ExerciseResult } from './api'

type Attempt = Pick<ExerciseDetail['attempts'][number], 'kind' | 'steps' | 'result'>

/** Must match MAX_ANSWER_CHARS in backend/exercises/services/common.py. */
export const MAX_ANSWER_CHARS = 4000

/** What to put back in the answer box: the last answer exactly as it was
 *  written, or, for one handed in before the text was kept, its steps one
 *  per line. */
export function draftText(attempts: Attempt[]): string {
  for (let i = attempts.length - 1; i >= 0; i--) {
    const a = attempts[i]
    if (a.kind === 'reveal') continue
    if (typeof a.result.text === 'string' && a.result.text) return a.result.text
    if (a.steps.length) return a.steps.join('\n')
  }
  return ''
}

/** The sentences of the last graded submit, to quote the one a grade points
 *  at even after the student has started editing the box. */
export function lastSubmitted(attempts: Attempt[]): string[] {
  for (let i = attempts.length - 1; i >= 0; i--) {
    if (attempts[i].kind === 'submit') return attempts[i].steps
  }
  return []
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

/** The option picked in the last submit, to show it again. */
export function lastChoice(attempts: Attempt[]): string | null {
  for (let i = attempts.length - 1; i >= 0; i--) {
    if (attempts[i].kind === 'submit') return attempts[i].result.answer ?? null
  }
  return null
}

/** Each statement's mark from the last submit; unmarked ones are left out. */
export function lastMarks(attempts: Attempt[]): Record<string, boolean> {
  for (let i = attempts.length - 1; i >= 0; i--) {
    if (attempts[i].kind !== 'submit') continue
    const out: Record<string, boolean> = {}
    for (const [label, mark] of Object.entries(attempts[i].result.answers ?? {})) {
      if (typeof mark === 'boolean') out[label] = mark
    }
    return out
  }
  return {}
}

export function allMarked(statements: { label: string }[], marks: Record<string, boolean>): boolean {
  return statements.length > 0 && statements.every((st) => typeof marks[st.label] === 'boolean')
}

/** A choice or the marks so far, as a line the hint can read. */
export function describeAnswer(kind: string, choice: string | null, marks: Record<string, boolean>): string {
  if (kind === 'choice') return choice ? `Picked ${choice}` : ''
  if (kind === 'true_false') {
    return Object.entries(marks).map(([label, mark]) => `${label}) ${mark ? 'true' : 'false'}`).join('; ')
  }
  return ''
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

type InSet = Listed & { set_key?: string; set_title?: string }
export type PracticeRow<T> =
  | { kind: 'one'; problem: T }
  | { kind: 'set'; key: string; title: string; problems: T[]; next: T; done: number; due: boolean; started: boolean }

/** The list as rows: problems picked together from one file are one row,
 *  where the first of them in the list would stand. `ordered` is the list
 *  already in practice order. A set's problems are in page order; `next` is
 *  the first one to do now (not mastered, not waiting to come back). */
export function practiceRows<T extends InSet>(ordered: T[]): PracticeRow<T>[] {
  const members = new Map<string, T[]>()
  for (const p of ordered) {
    if (p.set_key) members.set(p.set_key, [...(members.get(p.set_key) ?? []), p])
  }
  const rows: PracticeRow<T>[] = []
  const placed = new Set<string>()
  for (const p of ordered) {
    const set = p.set_key ? members.get(p.set_key)! : []
    if (set.length < 2) {
      rows.push({ kind: 'one', problem: p })
      continue
    }
    if (placed.has(p.set_key!)) continue
    placed.add(p.set_key!)
    const problems = [...set].sort((a, b) => a.id - b.id)
    const open = (q: T) => q.status === 'new' || (q.status === 'revisit' && q.due)
    const done = problems.filter((q) => q.status === 'mastered').length
    rows.push({
      kind: 'set', key: p.set_key!, title: p.set_title ?? '', problems,
      next: problems.find(open) ?? problems[0], done,
      due: problems.some((q) => q.status === 'revisit' && q.due),
      started: done > 0 || problems.some((q) => q.attempted || q.status === 'revisit'),
    })
  }
  return rows
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
