'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { Radio, X } from 'lucide-react'
import { liveAPI } from '@/lib/api'
import { getSocket } from '@/lib/realtime'

const DISMISSED = 'live-dismissed'

function readDismissed(): number[] {
  try {
    return JSON.parse(sessionStorage.getItem(DISMISSED) ?? '[]')
  } catch {
    return []
  }
}

/** "Someone opened a live round in one of your notebooks", wherever you are
 *  in the dashboard. Fetched once, then kept current by the socket. */
export function LiveInvites() {
  const t = useTranslations('live')
  const pathname = usePathname()
  const { data, mutate } = useSWR(['/live/rooms'], () => liveAPI.open())
  // The list needs the fetch, which only happens in the browser, so reading
  // storage here cannot make the first render differ from the server's.
  const [dismissed, setDismissed] = useState<number[]>(readDismissed)

  useEffect(() => {
    let cancelled = false
    let off = () => {}
    const reload = () => void mutate()
    void getSocket().then((s) => {
      if (cancelled || !s) return
      s.on('live:open', reload)
      s.on('live:closed', reload)
      off = () => {
        s.off('live:open', reload)
        s.off('live:closed', reload)
      }
    })
    return () => {
      cancelled = true
      off()
    }
  }, [mutate])

  const dismiss = (id: number) => {
    const next = [...dismissed, id]
    setDismissed(next)
    try {
      sessionStorage.setItem(DISMISSED, JSON.stringify(next))
    } catch {
      /* private mode: dismissed for this page only */
    }
  }

  const room = (data?.data.rooms ?? []).find((r) =>
    !dismissed.includes(r.id) &&
    !r.joined &&
    !pathname?.startsWith(`/dashboard/live/${r.id}`))
  if (!room) return null

  return (
    <div data-mode="quizzes" className="flex items-center gap-3 border-b border-mode/30 bg-mode/10 px-4 py-2.5 md:px-6" role="status">
      <Radio className="size-4 shrink-0 text-mode-ink" aria-hidden />
      <p className="min-w-0 flex-1 truncate text-sm text-slate-900">
        {t('invite', { host: room.host.name, notebook: room.notebook.title })}
      </p>
      <Link
        href={`/dashboard/live/${room.id}`}
        className="shrink-0 rounded-md bg-mode-strong px-3 py-1.5 text-sm font-medium text-mode-on hover:bg-mode-strong-hover focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
      >
        {t('enter')}
      </Link>
      <button
        type="button"
        onClick={() => dismiss(room.id)}
        aria-label={t('dismiss')}
        className="shrink-0 rounded p-1 text-mode-ink hover:bg-mode/20 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  )
}
