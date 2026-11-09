// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { askKey, batches, cardTexts, isShort, quizTexts, quizTitle, shownAs, toAsk, withOriginal } from './translate.ts'

test('each text is asked once, blanks never', () => {
  assert.deepEqual(toAsk(['Mitosis', '', '  ', 'Mitosis', 'Enzymes', undefined]), ['Mitosis', 'Enzymes'])
})

test('a long list goes in requests of at most the server limit', () => {
  const texts = Array.from({ length: 230 }, (_, i) => `t${i}`)
  const out = batches(texts, 100)
  assert.deepEqual(out.map((b) => b.length), [100, 100, 30])
  assert.deepEqual(out.flat(), texts)
})

test('a translation shows; the same words or none leave the original', () => {
  const found = new Map([['Phase Change Energy', 'Năng lượng chuyển pha'], ['DNA', 'DNA']])
  assert.equal(shownAs(found, 'Phase Change Energy'), 'Năng lượng chuyển pha')
  assert.equal(shownAs(found, 'DNA'), undefined)
  assert.equal(shownAs(found, 'Enzymes'), undefined)
  assert.equal(shownAs(undefined, 'Enzymes'), undefined)
})

// A short answer alone is a word without a sense ("Force" → "Buộc"), so it is
// asked with its question, and kept apart from the same word under another question.
const Q = 'What changes angular velocity?'

test('a short answer is one of up to four words, not a sentence', () => {
  assert.equal(isShort('kinetic energy'), true)
  assert.equal(isShort('Force'), true)
  assert.equal(isShort('Plants absorb carbon dioxide.'), false)
  assert.equal(isShort('the force applied at a distance from the axis'), false)
})

test('an answer asked with its question is its own entry', () => {
  assert.notEqual(askKey({ text: 'Force', context: Q }), askKey('Force'))
  assert.deepEqual(toAsk([{ text: 'Force', context: Q }, { text: 'Force', context: Q }, 'Force', { text: ' ', context: Q }]),
    [{ text: 'Force', context: Q }, 'Force'])
  const found = new Map([[askKey({ text: 'Force', context: Q }), 'Lực']])
  assert.equal(shownAs(found, 'Force', Q), 'Lực')
  assert.equal(shownAs(found, 'Force'), undefined)
})

test("a card asks for its question, its answer with the question, and its explanation", () => {
  assert.deepEqual(cardTexts({ question: Q, answer: 'Force', explanation: 'A torque is needed.' }),
    [Q, { text: 'Force', context: Q }, 'A torque is needed.'])
  const long = 'The force applied at a distance from the axis, called torque.'
  assert.deepEqual(cardTexts({ question: Q, answer: long }), [Q, long])
})

test('a quiz question asks for its text, each choice with the question, and its explanation', () => {
  const q = { question_text: 'Which divides the nucleus?', options: ['mitosis', 'meiosis'], explanation: 'Mitosis divides it.' }
  assert.deepEqual(quizTexts(q), [q.question_text, { text: 'mitosis', context: q.question_text },
    { text: 'meiosis', context: q.question_text }, 'Mitosis divides it.'])
})

test('true and false are the page words already, never asked', () => {
  assert.deepEqual(quizTexts({ question_text: 'Is air a conductor?', options: ['True', 'False'] }), ['Is air a conductor?'])
})

// The server names a quiz in English ("Quiz: Energy and waves", "Quiz: 3 sources");
// the page says it in its own words.
test("a quiz's stored name is read into what it is from", () => {
  assert.deepEqual(quizTitle('Quiz: Energy and waves'), { name: 'Energy and waves' })
  assert.deepEqual(quizTitle('Quiz: 3 sources'), { count: 3 })
  assert.deepEqual(quizTitle('My own practice set'), null)
})

test('inside a sentence a short answer reads as its translation with the original after it', () => {
  const found = new Map([[askKey({ text: 'Force', context: Q }), 'Lực']])
  assert.equal(withOriginal(found, 'Force', Q), 'Lực (Force)')
  assert.equal(withOriginal(found, 'Mass', Q), 'Mass')
})
