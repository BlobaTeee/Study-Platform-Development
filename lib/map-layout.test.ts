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
  // r0..r7 are one layer of eight, so it wraps: r0..r5 fill the first column
  // and r6, r7 start the second (drawn at rows 0 and 1). Counting by position
  // in the whole layer would put r7 at 7 and sort its dependant below r2's;
  // by drawn row r7 is at 1, above r2 at 2, so its dependant goes first.
  const roots = Array.from({ length: 8 }, (_, i) => `r${i}`)
  const keys = [...roots, 'dOf2', 'dOf7']
  const edges = [{ from: 'r2', to: 'dOf2' }, { from: 'r7', to: 'dOf7' }]
  const pos = layoutMap(keys, edges)
  assert.ok(pos.dOf7.y < pos.dOf2.y)
})

test('a key listed twice is placed once', () => {
  const pos = layoutMap(['a', 'a', 'b'], [])
  assert.deepEqual(Object.keys(pos).sort(), ['a', 'b'])
  assert.equal(pos.a.y, 0)
})
