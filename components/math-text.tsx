'use client'

import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { splitMath } from '@/lib/math-text'
import { cn } from '@/lib/utils'

/** Text as the student or the AI wrote it, with $...$ and $$...$$ typeset.
 *  A formula KaTeX cannot read is shown as its source in red, not dropped. */
export function MathText({ text, className }: { text: string; className?: string }) {
  const parts = useMemo(() => splitMath(text), [text])
  return (
    <span className={cn('whitespace-pre-line', className)}>
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
    </span>
  )
}
