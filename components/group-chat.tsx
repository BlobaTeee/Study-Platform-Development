'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, Send, Trash2 } from 'lucide-react'
import type { Socket } from 'socket.io-client'
import { notebooksAPI, type ChatMessage } from '@/lib/api'
import { getSocket } from '@/lib/realtime'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const TYPING_IDLE_MS = 2500

/** One group's thread: history over REST, new lines over the socket.
 *  Sending is a REST call on purpose — a message must survive a socket that
 *  is mid-reconnect — and the server broadcasts whatever it stores. */
export function GroupChat({ groupId, meId }: { groupId: number; meId?: number }) {
  const t = useTranslations('notebooks')
  const [messages, setMessages] = useState<ChatMessage[] | null>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [live, setLive] = useState(false)
  const [typing, setTyping] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [loadingOlder, setLoadingOlder] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const typingTimer = useRef<number | null>(null)

  const scrollToEnd = useCallback(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])

  useEffect(() => {
    let cancelled = false
    notebooksAPI
      .groupMessages(groupId)
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
  }, [groupId, t, scrollToEnd])

  // The socket is shared by the tab; this only subscribes and unsubscribes.
  useEffect(() => {
    let socket: Socket | null = null
    let cancelled = false

    const onNew = (m: ChatMessage) => {
      if (m.group !== groupId) return
      setMessages((prev) => {
        if (!prev) return prev
        if (prev.some((x) => x.id === m.id)) return prev      // our own echo
        return [...prev, m]
      })
      requestAnimationFrame(scrollToEnd)
    }
    const onDeleted = (d: { group: number; id: number }) => {
      if (d.group !== groupId) return
      setMessages((prev) => prev?.filter((m) => m.id !== d.id) ?? prev)
    }
    const onTyping = (d: { group: number; name: string }) => {
      if (d.group !== groupId) return
      setTyping(d.name)
      if (typingTimer.current) window.clearTimeout(typingTimer.current)
      typingTimer.current = window.setTimeout(() => setTyping(null), TYPING_IDLE_MS)
    }

    // The group's room is asked for here, not only on connecting: a group
    // made or joined after the socket connected was never delivered until a
    // reload (2026-11-26). After a reconnect it is asked for again, and the
    // thread is fetched again for whatever was said in between.
    const join = () => socket?.emit('group:join', { group: groupId })
    const onConnect = () => {
      setLive(true)
      join()
      notebooksAPI.groupMessages(groupId).then((res) => {
        if (!cancelled) setMessages(res.data.messages)
      }).catch(() => {})
    }
    const onDisconnect = () => setLive(false)

    void getSocket().then((s) => {
      if (cancelled || !s) return
      socket = s
      setLive(s.connected)
      if (s.connected) join()
      s.on('connect', onConnect)
      s.on('disconnect', onDisconnect)
      s.on('message:new', onNew)
      s.on('message:deleted', onDeleted)
      s.on('typing', onTyping)
    })

    return () => {
      cancelled = true
      if (typingTimer.current) window.clearTimeout(typingTimer.current)
      socket?.off('connect', onConnect)
      socket?.off('disconnect', onDisconnect)
      socket?.off('message:new', onNew)
      socket?.off('message:deleted', onDeleted)
      socket?.off('typing', onTyping)
    }
  }, [groupId, scrollToEnd])

  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    const body = draft.trim()
    if (!body || sending) return
    setSending(true)
    setError('')
    try {
      const res = await notebooksAPI.sendGroupMessage(groupId, body)
      setDraft('')
      setMessages((prev) => (prev?.some((m) => m.id === res.data.id) ? prev : [...(prev ?? []), res.data]))
      requestAnimationFrame(scrollToEnd)
    } catch {
      setError(t('chatFailed'))
    } finally {
      setSending(false)
    }
  }

  const announceTyping = () => {
    void getSocket().then((s) => s?.emit('typing', { group: groupId }))
  }

  const loadOlder = async () => {
    if (!messages?.length || loadingOlder) return
    setLoadingOlder(true)
    try {
      const res = await notebooksAPI.groupMessages(groupId, { before: messages[0].id })
      setMessages((prev) => [...res.data.messages, ...(prev ?? [])])
    } catch {
      setError(t('chatFailed'))
    } finally {
      setLoadingOlder(false)
    }
  }

  const remove = async (id: number) => {
    try {
      await notebooksAPI.deleteMessage(id)
      setMessages((prev) => prev?.filter((m) => m.id !== id) ?? prev)
    } catch {
      setError(t('chatFailed'))
    }
  }

  const mine = (m: ChatMessage) => m.author.is_you ?? (meId != null && m.author.user_id === meId)

  return (
    <section className="flex min-h-0 flex-1 flex-col" aria-label={t('chatTitle')}>
      <div className="flex items-baseline justify-end gap-3 px-1 pb-2">
        <span className={cn('inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-xs',
          live ? 'text-slate-600' : 'text-amber-700')}>
          <span
            className={cn('inline-block size-1.5 rounded-full', live ? 'bg-mode-analytics' : 'bg-amber-500')}
            aria-hidden
          />
          {live ? t('chatLive') : t('chatOffline')}
        </span>
      </div>

      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-slate-200 bg-white p-3">
        {messages === null ? (
          <div className="h-16 animate-pulse rounded bg-slate-100 motion-reduce:animate-none" aria-busy />
        ) : messages.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">{t('chatEmpty')}</p>
        ) : (
          <>
            {messages.length >= 50 && (
              <div className="pb-2 text-center">
                <Button type="button" variant="ghost" size="sm" disabled={loadingOlder} onClick={() => void loadOlder()}>
                  {loadingOlder ? <Loader2 className="animate-spin" aria-hidden /> : null}
                  {t('chatLoadOlder')}
                </Button>
              </div>
            )}
            <ol className="space-y-2.5">
              {messages.map((m) => (
                <li key={m.id} className={cn('group flex gap-2', mine(m) && 'flex-row-reverse')}>
                  <div className={cn('max-w-[78%] rounded-2xl px-3.5 py-2',
                    mine(m) ? 'bg-mode/10 text-slate-900' : 'bg-slate-100 text-slate-900')}>
                    {!mine(m) && <p className="text-xs font-medium text-slate-600">{m.author.name}</p>}
                    <p className="whitespace-pre-wrap break-words text-[15px] leading-relaxed">{m.body}</p>
                    <time className="mt-0.5 block font-mono text-[11px] text-slate-500" dateTime={m.created_at}>
                      {new Date(m.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                    </time>
                  </div>
                  {mine(m) && (
                    <button
                      type="button"
                      onClick={() => void remove(m.id)}
                      aria-label={t('chatDelete')}
                      className="self-center rounded-md p-1 text-slate-400 opacity-0 transition-opacity hover:text-mode-danger focus-visible:opacity-100 group-hover:opacity-100"
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                    </button>
                  )}
                </li>
              ))}
            </ol>
          </>
        )}
      </div>

      <p className="h-5 px-1 pt-1 text-xs text-slate-500" aria-live="polite">
        {typing ? t('chatTyping', { name: typing }) : ''}
      </p>

      <form onSubmit={send} className="mt-auto flex gap-2 pt-2">
        <input
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value)
            announceTyping()
          }}
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
    </section>
  )
}
