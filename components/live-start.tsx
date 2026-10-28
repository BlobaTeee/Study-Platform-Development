'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { liveAPI } from '@/lib/api'
import { cn } from '@/lib/utils'

const COUNTS = [5, 10, 15]
const SECONDS = [15, 20, 30, 60]

/** The notebook's way into a live round: join the one that is open, or open
 *  one with a question count and a time per question. */
export function LiveStart({ notebookId, memberCount, onClose }: { notebookId: number; memberCount: number; onClose: () => void }) {
  const t = useTranslations('live')
  const router = useRouter()
  const { data } = useSWR(['/live/rooms'], () => liveAPI.open())
  const open = data?.data.rooms.find((r) => r.notebook.id === notebookId)
  const [count, setCount] = useState(10)
  const [seconds, setSeconds] = useState(20)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const go = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await liveAPI.create(notebookId, { question_count: count, seconds })
      router.push(`/dashboard/live/${res.data.id}`)
    } catch (e) {
      const body = (e as { response?: { data?: { detail?: unknown; no_questions?: boolean } } }).response?.data
      setError(body?.no_questions ? t('noQuestions') : typeof body?.detail === 'string' ? body.detail : t('failed'))
      setBusy(false)
    }
  }

  return (
    <section className="mx-5 mt-4 shrink-0 rounded-xl border border-slate-200 bg-white p-5 md:mx-6 md:p-6" aria-labelledby="live-start-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-[60ch]">
          <h2 id="live-start-title" className="font-display text-lg font-semibold text-slate-900">{t('startTitle')}</h2>
          <p className="mt-1 text-base leading-relaxed text-slate-700">{t('startLead')}</p>
          {memberCount < 2 && <p className="mt-1 text-sm text-slate-700">{t('aloneNote')}</p>}
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>{t('close')}</Button>
      </div>

      {open ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-50 px-4 py-3">
          <p className="text-base text-slate-800">{t('roomOpen', { host: open.host.name, count: open.players })}</p>
          <Button onClick={() => void go()} disabled={busy}>
            {busy && <Loader2 className="animate-spin" aria-hidden />}
            {t('join')}
          </Button>
        </div>
      ) : (
        <form
          className="mt-4 space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            void go()
          }}
        >
          <Choice label={t('countLabel')} values={COUNTS} value={count} onChange={setCount} format={(n) => t('countValue', { count: n })} />
          <Choice label={t('secondsLabel')} values={SECONDS} value={seconds} onChange={setSeconds} format={(n) => t('secondsValue', { s: n })} />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="max-w-[52ch] text-sm text-slate-700">{t('groupFirst')}</p>
            <Button type="submit" disabled={busy}>
              {busy && <Loader2 className="animate-spin" aria-hidden />}
              {t('openRoom')}
            </Button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
    </section>
  )
}

function Choice({ label, values, value, onChange, format }: {
  label: string
  values: number[]
  value: number
  onChange: (n: number) => void
  format: (n: number) => string
}) {
  return (
    <fieldset>
      <legend className="text-sm font-medium text-slate-900">{label}</legend>
      <div className="mt-2 flex flex-wrap gap-2">
        {values.map((n) => (
          <button
            key={n}
            type="button"
            aria-pressed={value === n}
            onClick={() => onChange(n)}
            className={cn(
              'h-9 rounded-md border px-3 text-sm transition-colors duration-150 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 motion-reduce:transition-none',
              value === n ? 'border-mode-library bg-mode-library text-white' : 'border-slate-300 bg-white text-slate-800 hover:bg-slate-50'
            )}
          >
            {format(n)}
          </button>
        ))}
      </div>
    </fieldset>
  )
}
