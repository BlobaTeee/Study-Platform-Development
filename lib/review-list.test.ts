// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { reviewNotebooks, reviewSize } from './review-list.ts'

const empty = { owed: [], forgotten: [], mixUps: [], practice: [] }

test('the four lists meet under one entry per notebook', () => {
  const list = reviewNotebooks({
    owed: [{ notebook_id: 1, title: 'Sinh học 10', count: 5 }],
    forgotten: [{ notebook_id: 1, title: 'Sinh học 10', count: 9 }],
    mixUps: [{ notebook_id: 1, title: 'Sinh học 10', items: ['nguyên phân/giảm phân'] }],
    practice: [{ notebook_id: 1, title: 'Sinh học 10', total: 2 }],
  })
  assert.equal(list.length, 1)
  assert.equal(list[0].owed, 5)
  assert.equal(list[0].forgotten?.count, 9)
  assert.deepEqual(list[0].mixUps, ['nguyên phân/giảm phân'])
  assert.equal(reviewSize(list[0]), 17)
})

test('the biggest list comes first', () => {
  const list = reviewNotebooks({
    ...empty,
    owed: [{ notebook_id: 1, title: 'Hóa', count: 2 }, { notebook_id: 2, title: 'Sinh', count: 7 }],
  })
  assert.deepEqual(list.map((n) => n.title), ['Sinh', 'Hóa'])
})

test('loose cards and own problems stay apart, though neither has a notebook', () => {
  const list = reviewNotebooks({
    ...empty,
    forgotten: [{ notebook_id: null, title: '', count: 3 }],
    practice: [{ notebook_id: null, title: '', total: 1 }],
  })
  assert.deepEqual(list.map((n) => n.key).sort(), ['cards', 'own'])
})

test('a notebook with nothing to review is left out', () => {
  const list = reviewNotebooks({
    ...empty,
    owed: [{ notebook_id: 1, title: 'Sinh', count: 0 }],
    mixUps: [{ notebook_id: 2, title: 'Hóa', items: [] }],
  })
  assert.deepEqual(list, [])
})
