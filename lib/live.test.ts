// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { applyBroadcast, optionShares, secondsLeft, type LiveState } from './live.ts'

const base = (over: Partial<LiveState> = {}): LiveState => ({
  id: 1, notebook: { id: 2, title: 'Bio' }, host: { user_id: 7, name: 'Lan' },
  status: 'question', index: 0, total: 5, seconds: 20,
  players: [], question: { id: 3, text: 'Q?', type: 'multiple_choice', options: ['a', 'b'] },
  remaining_ms: 20000, answered_count: 0, reveal: null, next_open_ms: 0, results: [],
  you: { user_id: 9, is_host: false, joined: true, answer: 'a', missed: [] },
  ...over,
})

test('secondsLeft rounds up and never goes below zero', () => {
  assert.equal(secondsLeft(10_000, 0), 10)
  assert.equal(secondsLeft(10_000, 9_001), 1)
  assert.equal(secondsLeft(10_000, 12_000), 0)
})

test('optionShares keeps the options in order and splits the answers', () => {
  assert.deepEqual(optionShares({ b: 1, a: 3 }, ['a', 'b', 'c']), [
    { option: 'a', n: 3, share: 0.75 },
    { option: 'b', n: 1, share: 0.25 },
    { option: 'c', n: 0, share: 0 },
  ])
})

test('optionShares with no answers gives no shares', () => {
  assert.deepEqual(optionShares({}, ['a']), [{ option: 'a', n: 0, share: 0 }])
})

test('a broadcast keeps my own seat', () => {
  const { you, ...shared } = base({ answered_count: 1 })
  const next = applyBroadcast(base(), shared)
  assert.deepEqual(next.you, you)
  assert.equal(next.answered_count, 1)
})

test('a broadcast of the next question clears my answer', () => {
  const { you: _drop, ...shared } = base({ index: 1 })
  assert.equal(applyBroadcast(base(), shared).you.answer, null)
})

test('a broadcast of the reveal keeps my answer to show against the right one', () => {
  const { you: _drop, ...shared } = base({ status: 'reveal' })
  assert.equal(applyBroadcast(base(), shared).you.answer, 'a')
})

test('a broadcast that hands me the room makes me the host', () => {
  const { you: _drop, ...shared } = base({ host: { user_id: 9, name: 'Me' } })
  assert.equal(applyBroadcast(base(), shared).you.is_host, true)
})
