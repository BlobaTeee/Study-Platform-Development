'use client'

import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { splitFigures } from '@/lib/figures'
import { splitMath } from '@/lib/math-text'
import { cn } from '@/lib/utils'

/** Text as the student or the AI wrote it, with $...$ and $$...$$ typeset.
 *  A formula KaTeX cannot read is shown as its source in red, not dropped.
 *  A [Figure n: …] tag shows `figures[n - 1]`, the figure cut from the exam,
 *  or its description in brackets when there is none. */
export function MathText({ text, className, figures }: {
  text: string
  className?: string
  figures?: (string | null)[]
}) {
  const pieces = useMemo(() => splitFigures(text), [text])
  return (
    <span className={cn('whitespace-pre-line', className)}>
      {pieces.map((piece, i) => {
        if (piece.kind === 'text') return <Formulas key={i} text={piece.value} />
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
              __html: katex.renderToString(part.value, {
                displayMode: part.kind === 'display',
                throwOnError: false,
                errorColor: '#b91c1c',
                trust: false,
              }),
            }}
          />
        ),
      )}
    </>
  )
}
