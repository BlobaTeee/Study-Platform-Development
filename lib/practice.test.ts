// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { allMarked, describeAnswer, draftText, filtered, filtersFor, inPracticeOrder, lastChoice, lastGrade, lastHint, lastMarks, lastSubmitted, parseFilter, practiceRows, toRedo } from './practice.ts'

type A = { kind: 'submit' | 'hint' | 'reveal'; steps: string[]; result: Record<string, unknown> }
const at = (kind: A['kind'], steps: string[], result = {}) => ({ id: 0, created_at: '', kind, steps, result })

test('the grade and the hint shown are the latest of each', () => {
  const attempts = [at('submit', ['a'], { verdict: 'needs_work' }), at('hint', ['a'], { hint: 'h1' }),
    at('submit', ['a', 'b'], { verdict: 'passed' }), at('hint', ['a', 'b'], { hint: 'h2' })]
  assert.equal(lastGrade(attempts)?.verdict, 'passed')
  assert.equal(lastHint(attempts), 'h2')
  assert.equal(lastHint([]), null)
})

test('a hint asked before the last submit is not shown with its grade', () => {
  const attempts = [at('hint', ['a'], { hint: 'old' }), at('submit', ['a'], { verdict: 'needs_work', hint: 'new' })]
  assert.equal(lastHint(attempts), null)
})

test('problems to redo are the ones due again', () => {
  const p = (status: string, due: boolean) => ({ status, due })
  assert.equal(toRedo([p('revisit', true), p('revisit', false), p('new', false), p('mastered', false)]), 1)
})

type P = { id: number; status: 'new' | 'mastered' | 'revisit'; due: boolean; attempted: boolean;
  notebook_id: number | null; notebook_title: string; origin: 'document' | 'own' }
const prob = (id: number, over: Partial<P> = {}): P => ({ id, status: 'new', due: false, attempted: false,
  notebook_id: 1, notebook_title: 'Chemistry', origin: 'document', ...over })

test('what to do next comes first: due again, then started, then untouched, then done', () => {
  const list = [prob(1, { status: 'mastered' }), prob(2), prob(3, { status: 'revisit', due: true }),
    prob(4, { attempted: true }), prob(5, { status: 'revisit' }), prob(6)]
  assert.deepEqual(inPracticeOrder(list).map((p) => p.id), [3, 4, 6, 2, 5, 1])
})

test('a filter keeps one notebook, or only the problems brought in', () => {
  const list = [prob(1), prob(2, { notebook_id: 2, notebook_title: 'Biology' }),
    prob(3, { notebook_id: null, notebook_title: '', origin: 'own' })]
  assert.deepEqual(filtered(list, 'all').map((p) => p.id), [1, 2, 3])
  assert.deepEqual(filtered(list, 2).map((p) => p.id), [2])
  assert.deepEqual(filtered(list, 'own').map((p) => p.id), [3])
})

test('the filters are the notebooks that have problems, then own problems if any', () => {
  const list = [prob(1), prob(2), prob(3, { notebook_id: 2, notebook_title: 'Biology' }),
    prob(4, { notebook_id: null, notebook_title: '', origin: 'own' })]
  assert.deepEqual(filtersFor(list), [{ key: 1, title: 'Chemistry', count: 2 }, { key: 2, title: 'Biology', count: 1 },
    { key: 'own', title: '', count: 1 }])
  assert.deepEqual(filtersFor([prob(1)]), [{ key: 1, title: 'Chemistry', count: 1 }])
})

test('a filter read from the address bar is a notebook id, "own", or everything', () => {
  assert.equal(parseFilter('own'), 'own')
  assert.equal(parseFilter('12'), 12)
  assert.equal(parseFilter(null), 'all')
  assert.equal(parseFilter('x'), 'all')
})

test('the box gives the answer back exactly as it was written', () => {
  assert.equal(draftText([]), '')
  const written = 'HCMC: south-west monsoon. Hue: the mountains.\n\nSo they differ.'
  assert.equal(draftText([at('submit', ['HCMC: south-west monsoon.', 'Hue: the mountains.', 'So they differ.'], { text: written })]), written)
  assert.equal(draftText([at('submit', ['a'], { text: 'a' }), at('hint', ['a b'], { hint: 'h', text: 'a b' })]), 'a b')
})

test('an answer handed in before the text was kept comes back one step per line', () => {
  assert.equal(draftText([at('submit', ['a']), at('hint', ['a', 'b', 'c'])]), 'a\nb\nc')
  assert.equal(draftText([at('hint', ['a']), at('submit', ['a', 'c'])]), 'a\nc')
})

test('a reveal leaves the draft where it was', () => {
  assert.equal(draftText([at('submit', ['a', 'b']), at('reveal', [])]), 'a\nb')
})

test('the sentence a grade points at is quoted from the submit that was graded', () => {
  assert.deepEqual(lastSubmitted([at('submit', ['a', 'b']), at('hint', ['a', 'b', 'c'])]), ['a', 'b'])
  assert.deepEqual(lastSubmitted([at('hint', ['a'])]), [])
})

test('a keyed answer comes back as it was given', () => {
  const attempts = [at('submit', [], { verdict: 'needs_work', answer: 'C' }), at('hint', [], { hint: 'h' }),
    at('submit', [], { verdict: 'needs_work', answers: { a: true, b: null, c: false } })]
  assert.equal(lastChoice(attempts.slice(0, 2)), 'C')
  assert.deepEqual(lastMarks(attempts), { a: true, c: false })
  assert.deepEqual(lastMarks([]), {})
})

test('true/false is ready only when every statement is marked', () => {
  const statements = [{ label: 'a' }, { label: 'b' }]
  assert.equal(allMarked(statements, { a: true }), false)
  assert.equal(allMarked(statements, { a: true, b: false }), true)
  assert.equal(allMarked([], {}), false)
})

test('the hint is told what was picked or marked so far', () => {
  assert.equal(describeAnswer('choice', 'B', {}), 'Picked B')
  assert.equal(describeAnswer('choice', null, {}), '')
  assert.equal(describeAnswer('true_false', null, { a: true, b: false }), 'a) true; b) false')
})

test('problems picked from one file are one row, where the first of them stands', () => {
  const p = (id: number, set_key = '', status = 'new', due = false) => ({
    id, status, due, attempted: false, notebook_id: null, notebook_title: '', origin: 'own' as const,
    set_key, set_title: set_key ? 'Đề Hoá 12' : '',
  })
  const rows = practiceRows([p(9), p(5, 'a', 'mastered'), p(4, 'a'), p(7), p(6, 'a'), p(8, 'b')])
  assert.deepEqual(rows.map((r) => (r.kind === 'one' ? r.problem.id : r.key)), [9, 'a', 7, 8])
  const set = rows[1]
  assert.ok(set.kind === 'set')
  assert.deepEqual(set.problems.map((q) => q.id), [4, 5, 6])   // page order
  assert.equal(set.next.id, 4)
  assert.equal(set.done, 1)
  assert.equal(set.title, 'Đề Hoá 12')
  assert.ok(set.started && !set.due)
})
