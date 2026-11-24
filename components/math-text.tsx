'use client'

import { useMemo } from 'react'
import 'katex/dist/katex.min.css'
import { splitFigures } from '@/lib/figures'
import { splitMath } from '@/lib/math-text'
import { renderMath } from '@/lib/render-math'
import { splitTables } from '@/lib/tables'
import { cn } from '@/lib/utils'

/** Text as the student or the AI wrote it, with $...$ and $$...$$ typeset.
 *  A formula KaTeX cannot read is shown as its source in red, not dropped.
 *  A [Figure n: …] tag shows `figures[n - 1]`, the figure cut from the exam,
 *  or its description in brackets when there is none. A Markdown table is
 *  drawn as a table. */
export function MathText({ text, className, figures }: {
  text: string
  className?: string
  figures?: (string | null)[]
}) {
  const pieces = useMemo(() => splitFigures(text), [text])
  return (
    <span className={cn('whitespace-pre-line', className)}>
      {pieces.map((piece, i) => {
        if (piece.kind === 'text') return <TextAndTables key={i} text={piece.value} />
        const src = figures?.[piece.n - 1]
        return src ? (
          // A data URL cut from the student's own page: next/image adds nothing here.
          // eslint-disable-next-line @next/next/no-img-element
          <img key={i} src={src} alt={piece.description} title={piece.description}
               className="my-2 block h-auto max-h-80 max-w-full rounded-md border border-slate-200 bg-white" />
        ) : (
          <Formulas key={i} text={`[${piece.description}]`} />
        )
      })}
    </span>
  )
}

/** Text with its Markdown tables drawn as tables. Spans laid out as a table,
 *  not <table>: MathText often sits inside a <p>, where a table may not go. */
function TextAndTables({ text }: { text: string }) {
  const parts = useMemo(() => splitTables(text), [text])
  return (
    <>
      {parts.map((part, i) =>
        part.kind === 'text' ? (
          <Formulas key={i} text={part.value} />
        ) : (
          <span key={i} className="my-2 block max-w-full overflow-x-auto">
            <span role="table" className="table border-collapse text-sm">
              {part.header && (
                <span role="row" className="table-row bg-slate-50 font-medium">
                  {part.header.map((cell, c) => (
                    <span key={c} role="columnheader" className="table-cell border border-slate-300 px-2 py-1">
                      <Formulas text={cell} />
                    </span>
                  ))}
                </span>
              )}
              {part.rows.map((row, r) => (
                <span key={r} role="row" className="table-row">
                  {row.map((cell, c) => (
                    <span key={c} role="cell" className="table-cell border border-slate-300 px-2 py-1">
                      <Formulas text={cell} />
                    </span>
                  ))}
                </span>
              ))}
            </span>
          </span>
        ),
      )}
    </>
  )
}

function Formulas({ text }: { text: string }) {
  const parts = useMemo(() => splitMath(text), [text])
  return (
    <>
      {parts.map((part, i) =>
        part.kind === 'text' ? (
          <span key={i}>{part.value}</span>
        ) : (
          <span
            key={i}
            className={part.kind === 'display' ? 'my-2 block overflow-x-auto overflow-y-hidden' : undefined}
            dangerouslySetInnerHTML={{
              __html: renderMath(part.value, part.kind === 'display'),
            }}
          />
        ),
      )}
    </>
  )
}
