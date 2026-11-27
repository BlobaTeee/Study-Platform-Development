// A table in a problem read from an exam is written as a Markdown table, one
// row per line (backend/exercises/services/photo.py); the page draws it as a
// table instead of a run of "|" characters.

export type TableSegment =
  | { kind: 'text'; value: string }
  | { kind: 'table'; header: string[] | null; rows: string[][] }

const ROW = /^\s*\|.*\|\s*$/
const RULE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/

function cells(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
}

/** `text` cut into text and tables: two or more lines in a row that start
 *  and end with "|". A "|---|" line under the first row makes it a header.
 *  A "[Table]" line just above a table is the reader's marker and goes. */
export function splitTables(text: string): TableSegment[] {
  const lines = text.split('\n')
  const out: TableSegment[] = []
  let buffer: string[] = []
  const flush = () => {
    if (buffer.length) out.push({ kind: 'text', value: buffer.join('\n') })
    buffer = []
  }
  for (let i = 0; i < lines.length; ) {
    let j = i
    while (j < lines.length && (ROW.test(lines[j]) || RULE.test(lines[j]))) j++
    const block = lines.slice(i, j)
    if (block.filter((l) => ROW.test(l) && !RULE.test(l)).length >= 2 || (block.length >= 2 && RULE.test(block[1] ?? ''))) {
      // The table is a block of its own: no blank line before or after it.
      const blank = () => buffer.length > 0 && buffer[buffer.length - 1].trim() === ''
      while (blank()) buffer.pop()
      if (buffer.length && /^\s*\[Table\]\s*$/i.test(buffer[buffer.length - 1])) buffer.pop()
      while (blank()) buffer.pop()
      flush()
      const header = block.length > 1 && RULE.test(block[1]) ? cells(block[0]) : null
      const rows = block.slice(header ? 2 : 0).filter((l) => !RULE.test(l)).map(cells)
      out.push({ kind: 'table', header, rows })
      i = j
      while (i < lines.length && lines[i].trim() === '') i++
      continue
    }
    buffer.push(lines[i])
    i++
  }
  flush()
  return out
}
