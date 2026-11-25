// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { fileKind, keyedByFile, kindCounts } from './paper.ts'

test('a file is told by its type, or by its name when the browser gives none', () => {
  assert.equal(fileKind({ type: 'image/heic', name: 'a' }), 'image')
  assert.equal(fileKind({ type: '', name: 'De thi.PDF' }), 'pdf')
  assert.equal(fileKind({ type: '', name: 'de.docx' }), 'docx')
  assert.equal(fileKind({ type: 'text/plain', name: 'de.txt' }), null)
})

test('a paper is counted by kind', () => {
  assert.deepEqual(kindCounts([{ kind: 'choice' }, { kind: 'choice' }, { kind: 'short' }, {}]),
    { choice: 2, true_false: 0, short: 1, written: 1 })
})

test('a paper is keyed by its file only when every keyed question has an answer', () => {
  assert.equal(keyedByFile([{ kind: 'choice', answer: 'B' }, { kind: 'written' }]), true)
  assert.equal(keyedByFile([{ kind: 'choice', answer: 'B' }, { kind: 'short' }]), false)
  assert.equal(keyedByFile([{ kind: 'written' }]), false)
})
