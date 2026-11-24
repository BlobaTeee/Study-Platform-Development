// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { renderMath } from './render-math.ts'

// The letters KaTeX sets in maths italics, visible ones only (mhchem pads
// subscripts with an invisible \vphantom{X}).
function italics(html: string): string[] {
  const visible = html.split('katex-html')[1] ?? ''
  return [...visible.matchAll(/class="mord mathnormal"[^>]*>([^<]*)</g)].map((m) => m[1]).filter((c) => c !== 'X')
}

test('a chemical formula in \\ce is typeset upright, not as an error', () => {
  const html = renderMath('\\ce{CH3-CH(NH2)-COOH}', false)
  assert.ok(!html.includes('katex-error'))
  assert.deepEqual(italics(html), [])
})

test('plain maths still sets its letters in italics', () => {
  assert.deepEqual(italics(renderMath('x^2 + y', false)), ['x', 'y'])
})
