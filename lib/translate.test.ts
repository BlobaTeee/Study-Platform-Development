// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { askKey, batches, cardTexts, inPageLanguage, isShort, mapTexts, quizTexts, quizTitle, shownAs, toAsk } from './translate.ts'

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

const concept = (key: string, label: string, point: string, source_ids: number[]) => ({ key, label, point, source_ids })
const MAP = {
  concepts: [
    concept('1:0', 'Mitosis', 'Mitosis splits one nucleus into two.', [1]),
    concept('1:1', 'Chromosomes', 'Chromosomes carry DNA.', [1]),
    concept('2:0', 'Enzymes', 'Enzymes speed up reactions.', [2]),
  ],
  edges: [
    { from: '1:1', to: '1:0', why: 'Mitosis moves chromosomes.' },
    { from: '2:0', to: '1:0', why: 'Enzymes drive the cycle.' },
    { from: '2:0', to: '2:0', why: 'Elsewhere only.' },
  ],
}

test("a document's map asks for its own points and reasons, and every name", () => {
  assert.deepEqual(mapTexts(MAP, 1), [
    'Mitosis', 'Chromosomes', 'Enzymes',
    'Mitosis splits one nucleus into two.', 'Chromosomes carry DNA.',
    'Mitosis moves chromosomes.', 'Enzymes drive the cycle.',
  ])
})

test("the notebook's map asks for everything", () => {
  assert.equal(mapTexts(MAP).length, 3 + 3 + 3)
})

test('the map shows translations and keeps each original name for hover', () => {
  const found = new Map([['Mitosis', 'Nguyên phân'], ['Mitosis moves chromosomes.', 'Nguyên phân di chuyển nhiễm sắc thể.']])
  const shown = inPageLanguage(MAP, found)
  const original = (i: number) => (shown.concepts[i] as { original?: string }).original
  assert.equal(shown.concepts[0].label, 'Nguyên phân')
  assert.equal(original(0), 'Mitosis')
  assert.equal(shown.concepts[1].label, 'Chromosomes')
  assert.equal(original(1), undefined)
  assert.equal(shown.edges[0].why, 'Nguyên phân di chuyển nhiễm sắc thể.')
  assert.equal(inPageLanguage(MAP, undefined), MAP)
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
