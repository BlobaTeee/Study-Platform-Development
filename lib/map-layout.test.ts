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
