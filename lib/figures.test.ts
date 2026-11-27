// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { splitFigures, unplacedFigures } from './figures.ts'

test('a figure tag is cut out of the text', () => {
  assert.deepEqual(splitFigures('Câu 3. Cho hình\n[Figure 1: mạch carbon gắn vòng benzen]\nA. Xà phòng.'), [
    { kind: 'text', value: 'Câu 3. Cho hình\n' },
    { kind: 'figure', n: 1, description: 'mạch carbon gắn vòng benzen' },
    { kind: 'text', value: '\nA. Xà phòng.' },
  ])
})

test('brackets inside a description stay in it', () => {
  const parts = splitFigures('[Figure 2: đồ thị trên $[0; 1]$] rồi')
  assert.deepEqual(parts[0], { kind: 'figure', n: 2, description: 'đồ thị trên $[0; 1]$' })
  assert.deepEqual(parts[1], { kind: 'text', value: ' rồi' })
})

test('other brackets and an unclosed tag stay text', () => {
  assert.deepEqual(splitFigures('[On (-2; 0): y tăng]'), [{ kind: 'text', value: '[On (-2; 0): y tăng]' }])
  assert.deepEqual(splitFigures('a [Figure 1: không đóng'), [{ kind: 'text', value: 'a [Figure 1: không đóng' }])
})

test('figures whose tag the text lost are shown after it', () => {
  assert.deepEqual(unplacedFigures('[Figure 1: x] và chữ', ['a', 'b', null]), ['b'])
  assert.deepEqual(unplacedFigures('chữ', undefined), [])
})
