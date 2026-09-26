'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, Send } from 'lucide-react'
import type { Socket } from 'socket.io-client'
import { notebooksAPI, type DirectMessageRow } from '@/lib/api'
import { getSocket } from '@/lib/realtime'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** One private thread. Same shape as the group chat, minus the author
 *  names: in a thread of two, who said it is which side it sits on. */
export function DirectChat({ userId }: { userId: number }) {
  const t = useTranslations('notebooks')
  const [messages, setMessages] = useState<DirectMessageRow[] | null>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  const scrollToEnd = useCallback(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])

  useEffect(() => {
    let cancelled = false
    notebooksAPI
      .directThread(userId)
      .then((res) => {
        if (cancelled) return
        setMessages(res.data.messages)
        requestAnimationFrame(scrollToEnd)
      })
      .catch(() => {
        if (!cancelled) setError(t('chatFailed'))
      })
    return () => {
      cancelled = true
    }
  }, [userId, t, scrollToEnd])

  useEffect(() => {
    let socket: Socket | null = null
    let cancelled = false
    const onNew = (m: DirectMessageRow) => {
      if (m.with !== userId) return              // another thread's message
      setMessages((prev) => (prev && !prev.some((x) => x.id === m.id) ? [...prev, m] : prev))
      requestAnimationFrame(scrollToEnd)
    }
    void getSocket().then((s) => {
      if (cancelled || !s) return
      socket = s
      s.on('direct:new', onNew)
    })
    return () => {
      cancelled = true
      socket?.off('direct:new', onNew)
    }
  }, [userId, scrollToEnd])

  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    const body = draft.trim()
    if (!body || sending) return
    setSending(true)
    setError('')
    try {
      const res = await notebooksAPI.sendDirect(userId, body)
      setDraft('')
      setMessages((prev) => (prev?.some((m) => m.id === res.data.id) ? prev : [...(prev ?? []), res.data]))
      requestAnimationFrame(scrollToEnd)
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail || t('chatFailed'))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-slate-200 bg-white p-3">
        {messages === null ? (
          <div className="h-16 animate-pulse rounded bg-slate-100 motion-reduce:animate-none" aria-busy />
        ) : messages.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">{t('chatEmpty')}</p>
        ) : (
          <ol className="space-y-2.5">
            {messages.map((m) => (
              <li key={m.id} className={cn('flex', m.author.is_you && 'justify-end')}>
                <div
                  className={cn(
                    'max-w-[78%] rounded-2xl px-3.5 py-2',
                    m.author.is_you ? 'bg-mode/10 text-slate-900' : 'bg-slate-100 text-slate-900',
                  )}
                >
                  <p className="whitespace-pre-wrap break-words text-[15px] leading-relaxed">{m.body}</p>
                  <time className="mt-0.5 block font-mono text-[11px] text-slate-500" dateTime={m.created_at}>
                    {new Date(m.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                  </time>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>

      <form onSubmit={send} className="flex gap-2 pt-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t('chatPlaceholder')}
          maxLength={2000}
          className="h-10 min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 outline-none focus-visible:border-mode focus-visible:ring-[3px] focus-visible:ring-mode/25"
        />
        <Button type="submit" disabled={sending || !draft.trim()} aria-label={t('chatSend')}>
          {sending ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
        </Button>
      </form>

      {error && (
        <p role="alert" className="pt-1 text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  )
}
