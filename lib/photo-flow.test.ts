// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { asProblem, photoStep } from './photo-flow.ts'

test('before a photo has been read the student is on step 1', () => {
  assert.equal(photoStep({ questionCount: 0, picking: false }), 1)
})

test('a page with several questions stops at step 2 to choose one', () => {
  assert.equal(photoStep({ questionCount: 8, picking: true }), 2)
})

test('one question, or one chosen, goes to checking', () => {
  assert.equal(photoStep({ questionCount: 1, picking: false }), 3)
  assert.equal(photoStep({ questionCount: 8, picking: false }), 3)
})

test('a question keeps its section instruction on the first line', () => {
  assert.equal(asProblem({ label: 'Câu 1', instruction: 'Chọn đúng hoặc sai.', text: 'Cho $f(x)=x^3$.' }),
    'Chọn đúng hoặc sai.\nCho $f(x)=x^3$.')
  assert.equal(asProblem({ label: 'Câu 2', instruction: '', text: 'Tính $2+2$.' }), 'Tính $2+2$.')
})
