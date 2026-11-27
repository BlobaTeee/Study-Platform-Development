'use client'

import { useTranslations } from 'next-intl'
import { checkTyped, splitAtBlank } from '@/lib/cloze'
import { cn } from '@/lib/utils'

/** A quiz question with one word blanked out, typed in (moved here from
 *  flashcards on 2026-11-26). Before it is checked the blank shows what is
 *  being typed; after, it holds the answer, with a line on how close the
 *  typing came. Right or close (a missing accent, one slip) counts, as the
 *  server marks it (quizzes/services/paper.py typed_matches). */
export function FillBlank({ text, answer, typed, onType, onSubmit, checked }: {
  text: string
  /** The hidden word; only shown once checked. */
  answer: string | null
  typed: string
  onType: (value: string) => void
  onSubmit: () => void
  checked: boolean
}) {
  const t = useTranslations('quizzes')
  const [before, after] = splitAtBlank(text)
  const verdict = checked && answer !== null ? checkTyped(typed, answer) : null
  const right = verdict === 'correct' || verdict === 'close'
  return (
    <div className="space-y-6">
      <p className="text-2xl leading-relaxed text-slate-900 md:text-[1.75rem] text-pretty">
        {before}
        {checked && answer !== null ? (
          <mark className={cn('rounded px-1 font-semibold', right ? 'bg-emerald-100 text-emerald-950' : 'bg-amber-100 text-slate-900')}>
            {answer}
          </mark>
        ) : (
          <span className="inline-block min-w-[5ch] border-b-2 border-mode px-1 text-center text-mode-ink">
            {typed.trim() || ' '}
          </span>
        )}
        {after}
      </p>
      {checked ? (
        verdict && verdict !== 'empty' && (
          <p className={cn('text-base', verdict === 'wrong' ? 'text-red-800' : verdict === 'close' ? 'text-amber-800' : 'text-emerald-800')}>
            {t(`blank_${verdict}`, { typed: typed.trim() })}
          </p>
        )
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (typed.trim()) onSubmit()
          }}
        >
          <input
            autoFocus
            value={typed}
            onChange={(e) => onType(e.target.value)}
            placeholder={t('typeMissing')}
            aria-label={t('typeMissing')}
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            className="h-12 w-full rounded-lg border border-slate-300 bg-white px-4 text-lg text-slate-900 placeholder:text-slate-500 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
          />
        </form>
      )}
    </div>
  )
}

/** Whether a typed word counts, as the page and the server both mark it. */
export function blankCounts(typed: string, answer: string): boolean {
  const v = checkTyped(typed, answer)
  return v === 'correct' || v === 'close'
}
