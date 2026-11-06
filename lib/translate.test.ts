// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { batches, inPageLanguage, mapTexts, shownAs, toAsk } from './translate.ts'

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
