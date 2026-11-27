// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { splitTables } from './tables.ts'

test('a Markdown table becomes a table, its [Table] marker dropped', () => {
  const text = 'Cho bảng số liệu sau:\n\n[Table]\n| Cặp | $Zn^{2+}/Zn$ |\n| :--- | :--- |\n| E (V) | -0,762 |\n\na) Zn khử mạnh nhất.'
  assert.deepEqual(splitTables(text), [
    { kind: 'text', value: 'Cho bảng số liệu sau:' },
    { kind: 'table', header: ['Cặp', '$Zn^{2+}/Zn$'], rows: [['E (V)', '-0,762']] },
    { kind: 'text', value: 'a) Zn khử mạnh nhất.' },
  ])
})

test('a table without a header rule still is one', () => {
  assert.deepEqual(splitTables('| x | 1 |\n| y | 2 |'), [{ kind: 'table', header: null, rows: [['x', '1'], ['y', '2']] }])
})

test('one line between bars is text, as is $|x|$', () => {
  assert.deepEqual(splitTables('Tính $|x|$ khi\n| x | = 2'), [{ kind: 'text', value: 'Tính $|x|$ khi\n| x | = 2' }])
})
