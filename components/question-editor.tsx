'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'

export type EditableQuestion = {
  question_text: string
  options: string[]
  correct_answer: string
  explanation?: string
}

/** A generated question, opened for correction: the text, every option, which
 *  one is right, and the explanation. Saves the whole set at once. */
export function QuestionEditor({
  question,
  busy,
  error,
  onCancel,
  onSave,
}: {
  question: EditableQuestion
  busy: boolean
  error: string
  onCancel: () => void
  onSave: (patch: EditableQuestion) => void
}) {
  const t = useTranslations('quizzes')
  const common = useTranslations('common')
  const [text, setText] = useState(question.question_text)
  const [opts, setOpts] = useState<string[]>(question.options)
  const [correct, setCorrect] = useState(question.correct_answer)
  const [explanation, setExplanation] = useState(question.explanation ?? '')
  const fieldClass =
    'w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-lg text-slate-900 outline-none focus-visible:border-mode-quizzes focus-visible:ring-mode-quizzes/25 focus-visible:ring-[4px]'

  const trimmed = opts.map((o) => o.trim())
  const valid = text.trim() !== '' && trimmed.every((o) => o !== '') && trimmed.includes(correct.trim())

  return (
    <form
      className="rise rounded-2xl border border-slate-200 bg-white p-6 md:p-8 shadow-sheet space-y-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (!valid) return
        onSave({ question_text: text.trim(), options: trimmed, correct_answer: correct.trim(), explanation: explanation.trim() })
      }}
    >
      <label className="block space-y-1.5">
        <span className="font-mono text-sm font-semibold uppercase tracking-wide text-mode-quizzes">{t('questionLabel')}</span>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} autoFocus className={fieldClass} />
      </label>

      <fieldset className="space-y-2">
        <legend className="font-mono text-sm font-semibold uppercase tracking-wide text-slate-500 mb-1.5">{t('optionsLabel')}</legend>
        {opts.map((opt, i) => (
          <div key={i} className="flex items-center gap-3">
            <input
              type="radio"
              name="correct"
              aria-label={t('markCorrect')}
              checked={opt.trim() !== '' && opt.trim() === correct.trim()}
              onChange={() => setCorrect(opt)}
              className="size-4 accent-emerald-600 shrink-0"
            />
            <input
              value={opt}
              onChange={(e) => {
                const next = [...opts]
                next[i] = e.target.value
                setOpts(next)
                // Renaming the right option keeps it right.
                if (opt.trim() === correct.trim()) setCorrect(e.target.value)
              }}
              className={fieldClass}
            />
          </div>
        ))}
        <p className="text-sm text-slate-500">{t('optionsHint')}</p>
      </fieldset>

      <label className="block space-y-1.5">
        <span className="font-mono text-sm font-semibold uppercase tracking-wide text-slate-500">{t('explanationLabel')}</span>
        <textarea value={explanation} onChange={(e) => setExplanation(e.target.value)} rows={3} className={fieldClass} />
      </label>

      {error && <p role="alert" className="text-base text-red-700">{error}</p>}

      <div className="flex flex-wrap justify-end gap-3">
        <Button type="button" variant="outline" size="lg" className="h-11 text-base" disabled={busy} onClick={onCancel}>
          {common('cancel')}
        </Button>
        <Button type="submit" size="lg" className="h-11 text-base bg-mode-quizzes hover:bg-mode-quizzes-hover text-white" disabled={busy || !valid}>
          {common('save')}
        </Button>
      </div>
    </form>
  )
}
