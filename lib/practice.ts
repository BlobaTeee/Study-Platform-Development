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

type InSet = Listed & { set_key?: string; set_title?: string; source_id?: number | null; source_title?: string }
export type PracticeRow<T> =
  | { kind: 'one'; problem: T }
  | {
      kind: 'set'; key: string; title: string; problems: T[]; next: T; done: number; due: boolean; started: boolean
      // 'file': picked together from a photo or file (a set, renamable);
      // 'document': written from one document of a notebook.
      from: 'file' | 'document'
    }

/** Which row a problem belongs to: its set, or the document it was written
 *  from; '' for one that stands alone. */
function groupOf(p: InSet): string {
  if (p.set_key) return p.set_key
  return p.origin === 'document' && p.source_id ? `doc:${p.source_id}` : ''
}

/** The list as rows: problems picked together from one file are one row,
 *  and so are the problems written from one document, where the first of
 *  them in the list would stand. `ordered` is the list already in practice
 *  order. A row's problems are in the order they were made; `next` is the
 *  first one to do now (not mastered, not waiting to come back). */
export function practiceRows<T extends InSet>(ordered: T[]): PracticeRow<T>[] {
  const members = new Map<string, T[]>()
  for (const p of ordered) {
    const key = groupOf(p)
    if (key) members.set(key, [...(members.get(key) ?? []), p])
  }
  const rows: PracticeRow<T>[] = []
  const placed = new Set<string>()
  for (const p of ordered) {
    const key = groupOf(p)
    const set = key ? members.get(key)! : []
    if (set.length < 2) {
      rows.push({ kind: 'one', problem: p })
      continue
    }
    if (placed.has(key)) continue
    placed.add(key)
    const problems = [...set].sort((a, b) => a.id - b.id)
    const open = (q: T) => q.status === 'new' || (q.status === 'revisit' && q.due)
    const done = problems.filter((q) => q.status === 'mastered').length
    const fromFile = Boolean(p.set_key)
    rows.push({
      kind: 'set', key, title: (fromFile ? p.set_title : p.source_title) ?? '', problems,
      from: fromFile ? 'file' : 'document',
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
/** How many lines the list shows for these problems: a set, or the
 *  problems from one document, is one line (practiceRows). */
export function rowCount(problems: InSet[]): number {
  return new Set(problems.map((p) => groupOf(p) || `one:${p.id}`)).size
}

/** The notebooks (and "own") the list can be narrowed to, each with how
 *  many lines it shows, not how many problems: 83 read as a mistake beside
 *  six lines (2026-11-25). */
export function filtersFor(problems: InSet[]): { key: number | 'own'; title: string; count: number }[] {
  const out = new Map<number | 'own', { key: number | 'own'; title: string; count: number; lines: Set<string> }>()
  for (const p of problems) {
    const key = p.origin === 'own' || p.notebook_id == null ? 'own' : p.notebook_id
    const slot = out.get(key) ?? { key, title: key === 'own' ? '' : p.notebook_title, count: 0, lines: new Set<string>() }
    slot.lines.add(groupOf(p) || `one:${p.id}`)
    slot.count = slot.lines.size
    out.set(key, slot)
  }
  const own = out.get('own')
  out.delete('own')
  return [...out.values(), ...(own ? [own] : [])].map(({ key, title, count }) => ({ key, title, count }))
}

export function parseFilter(raw: string | null): PracticeFilter {
  if (raw === 'own') return 'own'
  const id = Number(raw)
  return raw && Number.isInteger(id) && id > 0 ? id : 'all'
}
