// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  addCard, addLink, blocker, freeSpot, pairId, removeCard, removeLink, tally,
  type BuildLink, type Card,
} from './map-build.ts'

const l = (from: string, to: string, why = ''): BuildLink => ({ from, to, why })
const card = (id: string, label: string, x = 0, y = 0): Card => ({ id, label, x, y })

test('a pair is the same pair whichever way it was linked', () => {
  assert.equal(pairId('a', 'b'), pairId('b', 'a'))
})

test('a link is added once, never to itself, never twice', () => {
  const one = addLink([], 'a', 'b')
  assert.deepEqual(one, [l('a', 'b')])
  assert.equal(addLink(one, 'b', 'a'), one)
  assert.equal(addLink(one, 'a', 'a'), one)
  assert.equal(addLink(one, 'a', 'c').length, 2)
})

test('a link is removed whichever way it is named', () => {
  assert.deepEqual(removeLink([l('a', 'b'), l('a', 'c')], 'b', 'a'), [l('a', 'c')])
})

test('a card is added once, trimmed, whatever its case', () => {
  const at = { x: 10, y: 20 }
  const one = addCard([], '  Nguyên   phân ', 'c1', at)
  assert.deepEqual(one, [card('c1', 'Nguyên phân', 10, 20)])
  assert.equal(addCard(one, 'nguyên PHÂN', 'c2', at), one)
  assert.equal(addCard(one, '   ', 'c3', at), one)
})

test('removing a card removes its links too', () => {
  const r = removeCard([card('a', 'A'), card('b', 'B'), card('c', 'C')], [l('a', 'b'), l('b', 'c'), l('a', 'c')], 'b')
  assert.deepEqual(r.cards.map((c) => c.id), ['a', 'c'])
  assert.deepEqual(r.links, [l('a', 'c')])
})

test('new cards are spread out and staggered, never on top of each other', () => {
  const size = { w: 100, h: 50, gapX: 60, gapY: 70 }
  assert.deepEqual(freeSpot([], 600, size), { x: 30, y: 30 })
  const placed: Card[] = []
  for (let i = 0; i < 5; i++) placed.push({ ...freeSpot(placed, 600, size), id: String(i), label: String(i) })
  // Across a row the cards step down and up, so a line between the first and
  // third does not run underneath the second; the row holds what fits.
  assert.deepEqual(placed.slice(0, 3).map((c) => [c.x, c.y]), [[30, 30], [190, 75], [350, 30]])
  assert.deepEqual([placed[3].x, placed[3].y], [30, 150])
  for (const a of placed)
    for (const b of placed)
      if (a !== b) assert.ok(Math.abs(a.x - b.x) >= 100 || Math.abs(a.y - b.y) >= 50, `${a.id} overlaps ${b.id}`)
})

test('what still stops a map from being sent, in order', () => {
  const three = [card('a', 'A'), card('b', 'B'), card('c', 'C')]
  assert.deepEqual(blocker([card('a', 'A')], []), { kind: 'cards', need: 2 })
  assert.deepEqual(blocker(three, []), { kind: 'links' })
  assert.deepEqual(blocker(three, [l('a', 'b', 'Both split.'), l('a', 'c', 'x')]), { kind: 'why', n: 2 })
  assert.equal(blocker(three, [l('a', 'b', 'Both split cells.')]), null)
})

test('the result is counted by verdict', () => {
  assert.deepEqual(tally([{ verdict: 'correct' }, { verdict: 'wrong' }, { verdict: 'correct' }, { verdict: 'partial' }]),
    { correct: 2, partial: 1, wrong: 1, unjudged: 0 })
})

test("a document's key points take the state of the concept that holds them", async () => {
  const { keyPointStates } = await import('./map-build.ts')
  const concepts = [
    { members: ['7:0', '9:3'], state: 'weak' as const },
    { members: ['7:2'], state: 'strong' as const },
  ]
  assert.deepEqual(keyPointStates(concepts, 7, 3), ['weak', null, 'strong'])
})
