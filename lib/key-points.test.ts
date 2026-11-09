// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { keyPointStates } from './key-points.ts'

test("a document's key points take the state of the concept that holds them", () => {
  const concepts = [
    { members: ['7:0', '9:3'], state: 'weak' as const },
    { members: ['7:2'], state: 'strong' as const },
  ]
  assert.deepEqual(keyPointStates(concepts, 7, 3), ['weak', null, 'strong'])
})
