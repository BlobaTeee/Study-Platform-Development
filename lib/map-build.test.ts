// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { addLink, pairId, readyToSend, removeLink, tally, type BuildLink } from './map-build.ts'

const l = (from: string, to: string, why = ''): BuildLink => ({ from, to, why })

test('a pair is the same pair whichever way it was linked', () => {
  assert.equal(pairId('a', 'b'), pairId('b', 'a'))
})

test('a new link is added once, never to itself, never twice', () => {
  const one = addLink([], 'a', 'b')
  assert.deepEqual(one, [l('a', 'b')])
  assert.equal(addLink(one, 'b', 'a'), one)
  assert.equal(addLink(one, 'a', 'a'), one)
  assert.equal(addLink(one, 'a', 'c').length, 2)
})

test('a link is removed whichever way it is named', () => {
  assert.deepEqual(removeLink([l('a', 'b'), l('a', 'c')], 'b', 'a'), [l('a', 'c')])
})

test('a round can be sent once every link has a reason', () => {
  assert.equal(readyToSend([]), false)
  assert.equal(readyToSend([l('a', 'b', 'ok')]), false)
  assert.equal(readyToSend([l('a', 'b', 'Both split cells.')]), true)
  assert.equal(readyToSend([l('a', 'b', 'Both split cells.'), l('a', 'c', '  ')]), false)
})

test('the result is counted by verdict', () => {
  assert.deepEqual(tally([{ verdict: 'correct' }, { verdict: 'wrong' }, { verdict: 'correct' }, { verdict: 'partial' }]),
    { correct: 2, partial: 1, wrong: 1, unjudged: 0 })
})
