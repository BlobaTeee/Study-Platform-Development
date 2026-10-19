// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { draftSteps, filtered, filtersFor, inPracticeOrder, lastGrade, lastHint, parseFilter, toRedo } from './practice.ts'

type A = { kind: 'submit' | 'hint' | 'reveal'; steps: string[]; result: Record<string, unknown> }
const at = (kind: A['kind'], steps: string[], result = {}) => ({ id: 0, created_at: '', kind, steps, result })

test('a fresh problem starts with one empty step', () => {
  assert.deepEqual(draftSteps([]), [''])
})

test('the draft picks up from the last thing handed in, hint or submit', () => {
  assert.deepEqual(draftSteps([at('submit', ['a']), at('hint', ['a', 'b'])]), ['a', 'b'])
  assert.deepEqual(draftSteps([at('hint', ['a']), at('submit', ['a', 'c'])]), ['a', 'c'])
})

test('a reveal leaves the draft where it was', () => {
  assert.deepEqual(draftSteps([at('submit', ['a', 'b']), at('reveal', [])]), ['a', 'b'])
})

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
