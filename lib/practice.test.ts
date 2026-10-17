// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { draftSteps, lastGrade, lastHint, toRedo } from './practice.ts'

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
