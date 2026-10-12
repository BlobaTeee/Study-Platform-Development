'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { reviewsAPI, type MisconceptionNotebook } from '@/lib/api'

/** What the student keeps confusing, named from the wrong options they chose
 *  in two or more questions. Fixed by setting the two ideas side by side:
 *  the button makes those contrast cards once and opens them. */
export function Misconceptions({ notebooks }: { notebooks: MisconceptionNotebook[] }) {
  const t = useTranslations('analytics')
  const router = useRouter()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')

  const practise = async (notebookId: number, key: string) => {
    setBusy(key)
    setError('')
    try {
      const res = await reviewsAPI.practiseMisconception(notebookId, key)
      router.push(`/dashboard/flashcards?cards=${res.data.card_ids.join(',')}`)
    } catch {
      setError(t('misconceptionFailed'))
      setBusy(null)
    }
  }

  return (
    <div className="mt-3 space-y-3">
      <ul className="divide-y divide-slate-100">
        {notebooks.flatMap((nb) =>
          nb.items.map((item) => (
            <li key={`${nb.notebook_id}-${item.key}`} className="flex flex-col items-start gap-3 py-4 sm:flex-row sm:items-center sm:gap-6">
              <div className="min-w-0 flex-1">
                <p className="text-base text-slate-900">
                  {t.rich('mixUp', {
                    a: item.confused,
                    b: item.with,
                    strong: (chunk) => <span className="font-semibold">{chunk}</span>,
                  })}
                </p>
                {item.difference && <p className="mt-1 max-w-[65ch] text-sm leading-relaxed text-slate-700">{item.difference}</p>}
                <p className="mt-1 text-xs text-slate-500">
                  {t('mixUpEvidence', { count: item.evidence })}
                  {nb.title ? ` · ${nb.title}` : ''}
                </p>
              </div>
              <Button variant="outline" size="sm" className="shrink-0" disabled={busy !== null}
                onClick={() => void practise(nb.notebook_id, item.key)}>
                {busy === item.key ? <Loader2 className="animate-spin" aria-hidden /> : null}
                {t('contrastCards')}
              </Button>
            </li>
          ))
        )}
      </ul>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </div>
  )
}
