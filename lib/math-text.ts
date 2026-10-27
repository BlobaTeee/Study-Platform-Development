// Text with LaTeX maths in it ($...$ inline, $$...$$ on its own line), as
// the photo reader writes it. Cut into pieces so the maths can be typeset
// and the rest shown as it was typed.

export type MathSegment = { kind: 'text' | 'inline' | 'display'; value: string }

const ESCAPED = '\u0000'

// Pandoc's rule, so a price is not maths: "$" opens only before a non-space,
// closes only after a non-space and not before a digit.
function closingDollar(text: string, from: number): number {
  for (let i = from; i < text.length; i++) {
    if (text[i] === '\n') return -1
    if (text[i] === '$' && !/\s/.test(text[i - 1]) && !/\d/.test(text[i + 1] ?? '')) return i
  }
  return -1
}

export function splitMath(raw: string): MathSegment[] {
  const text = raw.replace(/\\\$/g, ESCAPED)
  const out: MathSegment[] = []
  let plain = ''
  let i = 0

  const flush = () => {
    if (plain) out.push({ kind: 'text', value: plain.replaceAll(ESCAPED, '$') })
    plain = ''
  }

  while (i < text.length) {
    if (text.startsWith('$$', i)) {
      const end = text.indexOf('$$', i + 2)
      if (end > i + 2) {
        flush()
        out.push({ kind: 'display', value: text.slice(i + 2, end).trim().replaceAll(ESCAPED, '\\$') })
        i = end + 2
        continue
      }
    } else if (text[i] === '$' && text[i + 1] && !/\s/.test(text[i + 1])) {
      const end = closingDollar(text, i + 2)
      if (end > 0) {
        flush()
        out.push({ kind: 'inline', value: text.slice(i + 1, end).replaceAll(ESCAPED, '\\$') })
        i = end + 1
        continue
      }
    }
    plain += text[i]
    i++
  }
  flush()
  return out
}

export function hasMath(text: string): boolean {
  return splitMath(text).some((s) => s.kind !== 'text')
}
