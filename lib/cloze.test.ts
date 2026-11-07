// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { checkTyped, checkTypedAny, splitAtBlank, suggestedGrade } from './cloze.ts'

test('the exact word is correct, whatever the case and spacing', () => {
  assert.equal(checkTyped('  Hiệu   Quả ', 'hiệu quả'), 'correct')
  assert.equal(checkTyped('effective.', 'effective'), 'correct')
})

test('the right word without its accents is close, not wrong', () => {
  assert.equal(checkTyped('hieu qua', 'hiệu quả'), 'close')
  assert.equal(checkTyped('dien thoai', 'điện thoại'), 'close')
})

test('one slip in a longer word is close', () => {
  assert.equal(checkTyped('efective', 'effective'), 'close')
  assert.equal(checkTyped('usabilty', 'usability'), 'close')
})

test('a short word gets no slack: one letter changes it', () => {
  assert.equal(checkTyped('cat', 'car'), 'wrong')
})

test('a different word is wrong, and nothing typed is no answer', () => {
  assert.equal(checkTyped('efficient', 'effective'), 'wrong')
  assert.equal(checkTyped('hiệu lực', 'hiệu quả'), 'wrong')
  assert.equal(checkTyped('   ', 'effective'), 'empty')
})

test('a wrong answer suggests Hard, a right or nearly right one Good', () => {
  assert.equal(suggestedGrade('wrong'), 'hard')
  assert.equal(suggestedGrade('close'), 'good')
  assert.equal(suggestedGrade('correct'), 'good')
  assert.equal(suggestedGrade('empty'), null)
})

test('the sentence splits around its one blank', () => {
  assert.deepEqual(splitAtBlank('A product is ___, safe.'), ['A product is ', ', safe.'])
  assert.deepEqual(splitAtBlank('No blank here'), ['No blank here', ''])
})

test('the word in either language counts: the best of the two checks', () => {
  assert.equal(checkTypedAny('động năng', ['kinetic energy', 'động năng']), 'correct')
  assert.equal(checkTypedAny('dong nang', ['kinetic energy', 'động năng']), 'close')
  assert.equal(checkTypedAny('kinetic energy', ['kinetic energy', 'động năng']), 'correct')
  assert.equal(checkTypedAny('thế năng', ['kinetic energy', 'động năng']), 'wrong')
  assert.equal(checkTypedAny('  ', ['kinetic energy']), 'empty')
})
