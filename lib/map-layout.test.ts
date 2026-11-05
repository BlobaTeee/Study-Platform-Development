// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { CARD_H, CARD_W, layoutMap } from './map-layout.ts'

const overlap = (a: { x: number; y: number }, b: { x: number; y: number }) =>
  Math.abs(a.x - b.x) < CARD_W && Math.abs(a.y - b.y) < CARD_H

test('the same data always gives the same picture', () => {
  const keys = ['a', 'b', 'c', 'd']
  const edges = [{ from: 'a', to: 'c' }, { from: 'b', to: 'c' }, { from: 'c', to: 'd' }]
  assert.deepEqual(layoutMap(keys, edges), layoutMap(keys, edges))
})

test('a prerequisite sits left of what depends on it', () => {
  const pos = layoutMap(['a', 'b', 'c'], [{ from: 'a', to: 'b' }, { from: 'b', to: 'c' }])
  assert.ok(pos.a.x < pos.b.x && pos.b.x < pos.c.x)
})

test('no two cards overlap, even with many concepts and no links', () => {
  const keys = Array.from({ length: 45 }, (_, i) => `k${i}`)
  const pos = layoutMap(keys, [])
  for (let i = 0; i < keys.length; i++)
    for (let j = i + 1; j < keys.length; j++) assert.ok(!overlap(pos[keys[i]], pos[keys[j]]), `${keys[i]} ${keys[j]}`)
  const rows = new Set(keys.map((k) => pos[k].y)).size
  assert.ok(rows <= 14, 'wraps into columns instead of one tall column')
})

test('links to unknown cards are ignored', () => {
  const pos = layoutMap(['a'], [{ from: 'x', to: 'a' }])
  assert.deepEqual(Object.keys(pos), ['a'])
})

test('a cycle gives the same columns whatever order the keys come in', () => {
  const edges = [{ from: 'a', to: 'b' }, { from: 'b', to: 'c' }, { from: 'c', to: 'a' }, { from: 'c', to: 'd' }]
  const one = layoutMap(['a', 'b', 'c', 'd'], edges)
  const two = layoutMap(['d', 'c', 'b', 'a'], edges)
  for (const k of ['a', 'b', 'c', 'd']) assert.equal(one[k].x, two[k].x, k)
  assert.ok(one.a.x < one.b.x && one.b.x < one.c.x && one.c.x < one.d.x)
})

test('two cards that point at each other keep the first link', () => {
  const edges = [{ from: 'a', to: 'b' }, { from: 'b', to: 'a' }]
  for (const keys of [['a', 'b'], ['b', 'a']]) {
    const pos = layoutMap(keys, edges)
    assert.ok(pos.a.x < pos.b.x)
  }
})

test('order in a tall layer follows the rows its cards are drawn at', () => {
  // r0..r7 all lead on, so one layer of eight wraps: r0, r1 fill the short
  // first column and r2..r7 the second (r2 drawn at row 0). Counting by
  // position in the whole layer would put r2 at 2 and sort its dependant
  // below r1's; by drawn row r2 is at 0, above r1 at 1, so its dependant
  // goes first.
  const roots = Array.from({ length: 8 }, (_, i) => `r${i}`)
  const keys = [...roots, 'dOf1', 'dOf2', 'rest']
  const edges = [
    { from: 'r1', to: 'dOf1' },
    { from: 'r2', to: 'dOf2' },
    ...['r0', 'r3', 'r4', 'r5', 'r6', 'r7'].map((from) => ({ from, to: 'rest' })),
  ]
  const pos = layoutMap(keys, edges)
  assert.ok(pos.r1.x < pos.r2.x && pos.r2.y < pos.r1.y)
  assert.ok(pos.dOf2.y < pos.dOf1.y)
})

test('in a layer that wraps, concepts that lead on sit next to what they lead to', () => {
  // Ten first-layer concepts, three with a dependant: those three go in the
  // layer's last column, so no arrow runs under another first-layer card.
  const roots = Array.from({ length: 10 }, (_, i) => `r${i}`)
  const edges = ['r0', 'r4', 'r8'].map((from) => ({ from, to: `dOf${from}` }))
  const pos = layoutMap([...roots, ...edges.map((e) => e.to)], edges)
  const lastRootColumn = Math.max(...roots.map((k) => pos[k].x))
  for (const e of edges) {
    assert.equal(pos[e.from].x, lastRootColumn, e.from)
    assert.ok(pos[e.to].x > lastRootColumn)
  }
})

test('a key listed twice is placed once', () => {
  const pos = layoutMap(['a', 'a', 'b'], [])
  assert.deepEqual(Object.keys(pos).sort(), ['a', 'b'])
  assert.equal(pos.a.y, 0)
})

test('smaller cards are laid out on a smaller grid', async () => {
  const { layoutMap, SMALL_CARD } = await import('./map-layout.ts')
  const pos = layoutMap(['a', 'b', 'c'], [{ from: 'a', to: 'b' }], SMALL_CARD)
  assert.equal(pos.b.x - pos.a.x, SMALL_CARD.w + SMALL_CARD.gapX)
  const big = layoutMap(['a', 'b', 'c'], [{ from: 'a', to: 'b' }])
  assert.ok(big.b.x - big.a.x > pos.b.x - pos.a.x)
})
