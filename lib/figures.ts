// A figure in a problem read from an exam page is written as
// [Figure n: what it shows] (backend/exercises/services/figures.py). The page
// shows the figure cut from the exam in its place; the words stay for the
// grader, and show only when there is no picture.

export type FigureSegment = { kind: 'text'; value: string } | { kind: 'figure'; n: number; description: string }

const OPEN = /\[Figure\s*(\d+)\s*:/g

/** `text` cut into text and figure tags. A description may hold brackets of
 *  its own ("$[0; 1]$"), so the tag ends at the bracket that balances it. */
export function splitFigures(text: string): FigureSegment[] {
  const out: FigureSegment[] = []
  let last = 0
  OPEN.lastIndex = 0
  for (let m = OPEN.exec(text); m; m = OPEN.exec(text)) {
    let depth = 1
    let i = m.index + m[0].length
    for (; i < text.length && depth > 0; i++) {
      if (text[i] === '[') depth++
      else if (text[i] === ']') depth--
    }
    if (depth !== 0) break                       // never closed: leave it as text
    if (m.index > last) out.push({ kind: 'text', value: text.slice(last, m.index) })
    out.push({ kind: 'figure', n: Number(m[1]), description: text.slice(m.index + m[0].length, i - 1).trim() })
    last = i
    OPEN.lastIndex = i
  }
  if (last < text.length) out.push({ kind: 'text', value: text.slice(last) })
  return out
}

/** The figures a text does not place itself (the model dropped its tag), to
 *  show after it, so a cut figure is never lost. */
export function unplacedFigures(text: string, figures: (string | null)[] | undefined): string[] {
  if (!figures?.length) return []
  const placed = new Set(splitFigures(text).flatMap((s) => (s.kind === 'figure' ? [s.n] : [])))
  return figures.flatMap((src, i) => (src && !placed.has(i + 1) ? [src] : []))
}
