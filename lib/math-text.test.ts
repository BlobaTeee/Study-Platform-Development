// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { firstLines, hasMath, splitMath } from './math-text.ts'

test('plain text is one text segment', () => {
  assert.deepEqual(splitMath('Solve for x.'), [{ kind: 'text', value: 'Solve for x.' }])
})

test('inline and display maths are cut out of the text', () => {
  assert.deepEqual(splitMath(String.raw`Tính $\int_0^1 x^2\,dx$ và $$\frac{a}{b}$$ nhé`), [
    { kind: 'text', value: 'Tính ' },
    { kind: 'inline', value: String.raw`\int_0^1 x^2\,dx` },
    { kind: 'text', value: ' và ' },
    { kind: 'display', value: String.raw`\frac{a}{b}` },
    { kind: 'text', value: ' nhé' },
  ])
})

test('a lone dollar sign, as in a price, stays text', () => {
  assert.deepEqual(splitMath('It costs $20 per month'), [{ kind: 'text', value: 'It costs $20 per month' }])
  assert.equal(hasMath('It costs $20 per month'), false)
})

test('two prices in one sentence are not read as maths', () => {
  assert.equal(hasMath('Shirts cost $20 and hats $15.'), false)
})

test('an escaped dollar is a dollar', () => {
  assert.deepEqual(splitMath(String.raw`Pay \$5 now`), [{ kind: 'text', value: 'Pay $5 now' }])
})

test('hasMath sees real maths', () => {
  assert.equal(hasMath(String.raw`Find $x^2$`), true)
  assert.equal(hasMath('$$a+b$$'), true)
})

test('firstLines gives a short one-line preview', () => {
  assert.equal(firstLines('Câu hỏi\nA. 1\nB. 2'), 'Câu hỏi A. 1 B. 2')
  assert.equal(firstLines('word '.repeat(60)).length <= 121, true)
  assert.ok(firstLines('word '.repeat(60)).endsWith('…'))
})

test('firstLines never cuts a formula in half', () => {
  const text = 'a'.repeat(110) + String.raw` $\frac{x^2 - 1}{x + 2}$ and more`
  const preview = firstLines(text)
  assert.ok(!preview.includes(String.raw`$\frac{x^2`) || preview.includes(String.raw`{x + 2}$`))
  assert.ok(preview.endsWith('…'))
})
