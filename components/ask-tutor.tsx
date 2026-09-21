'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, MessageCircleQuestion, Send } from 'lucide-react'
import { flashcardsAPI, type TutorTurn } from '@/lib/api'

const MAX_TURNS = 3

/** A tutor for one card, shown only once its answer is on screen. Three
 *  questions, answered from the card's own passage; the thread lives in
 *  this component and resets with the card (keyed by the parent). */
export function AskTutor({ cardId }: { cardId: number }) {
  const t = useTranslations('flashcards')
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<TutorTurn[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const asked = turns.filter((x) => x.role === 'user').length
  const left = MAX_TURNS - asked

  const ask = async (question: string) => {
    const q = question.trim()
    if (!q || busy || left <= 0) return
    setBusy(true)
    setError('')
    setDraft('')
    try {
      const res = await flashcardsAPI.askTutor(cardId, { question: q, history: turns })
      setTurns((prev) => [...prev, { role: 'user', text: q }, { role: 'tutor', text: res.data.answer }])
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail || t('tutorFailed'))
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <div className="flex justify-center">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900"
        >
          <MessageCircleQuestion className="size-4" aria-hidden />
          {t('askTutor')}
        </button>
      </div>
    )
  }

  return (
    <div className="rise rounded-2xl border border-slate-200 bg-white p-5 shadow-sheet space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-slate-500 inline-flex items-center gap-1.5">
          <MessageCircleQuestion className="size-3.5" aria-hidden />
          {t('tutorTitle')}
        </p>
        <span className="font-mono text-xs text-slate-400 tabular-nums shrink-0 whitespace-nowrap">{t("questionsLeft", { count: left })}</span>
      </div>

      {turns.length > 0 && (
        <ol className="space-y-3">
          {turns.map((turn, i) => (
            <li
              key={i}
              className={
                turn.role === 'user'
                  ? 'text-base text-slate-900 font-medium'
                  : 'rounded-lg bg-slate-50 px-4 py-3 text-base text-slate-700 leading-relaxed'
              }
            >
              {turn.text}
            </li>
          ))}
        </ol>
      )}

      {busy && (
        <p className="inline-flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="size-4 animate-spin" aria-hidden /> {t('tutorThinking')}
        </p>
      )}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}

      {left > 0 ? (
        <>
          {turns.length === 0 && (
            <div className="flex flex-wrap gap-2">
              {(['promptSimpler', 'promptExample', 'promptWhyNot'] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  disabled={busy}
                  onClick={() => void ask(t(k))}
                  className="rounded-full border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {t(k)}
                </button>
              ))}
            </div>
          )}
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              void ask(draft)
            }}
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={t('tutorPlaceholder')}
              maxLength={500}
              disabled={busy}
              className="h-11 flex-1 min-w-0 rounded-lg border border-slate-300 px-3.5 text-base text-slate-900 outline-none focus-visible:border-mode focus-visible:ring-mode/25 focus-visible:ring-[4px]"
            />
            <button
              type="submit"
              disabled={busy || !draft.trim()}
              aria-label={t('send')}
              className="grid size-11 shrink-0 place-items-center rounded-lg bg-mode text-white hover:bg-mode-hover disabled:opacity-50"
            >
              <Send className="size-4" aria-hidden />
            </button>
          </form>
        </>
      ) : (
        <p className="text-sm text-slate-500">{t('tutorDone')}</p>
      )}
    </div>
  )
}
