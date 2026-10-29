// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { loadFailure } from './load-error.ts'

test('no response at all means the server could not be reached', () => {
  assert.deepEqual(loadFailure({ message: 'Network Error', code: 'ERR_NETWORK' }), { kind: 'offline' })
  assert.deepEqual(loadFailure({ request: {}, message: 'timeout of 0ms exceeded' }), { kind: 'offline' })
})

test('a 5xx is the server failing, not the network', () => {
  assert.deepEqual(loadFailure({ response: { status: 503 } }), { kind: 'server', status: 503 })
})

test('anything else keeps its status so it can be read', () => {
  assert.deepEqual(loadFailure({ response: { status: 403 } }), { kind: 'other', status: 403 })
})

test('something that is not an HTTP error at all is still reported', () => {
  assert.deepEqual(loadFailure(new TypeError('x is undefined')), { kind: 'other', status: null })
})
