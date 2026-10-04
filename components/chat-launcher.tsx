'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronLeft, MessageCircle, Plus, UserRound, Users, X } from 'lucide-react'
import type { Socket } from 'socket.io-client'
import { notebooksAPI, type ChatLastLine, type ChatOverview } from '@/lib/api'
import { getSocket } from '@/lib/realtime'
import { GroupChat } from '@/components/group-chat'
import { DirectChat } from '@/components/direct-chat'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type Open = { kind: 'group'; id: number; title: string } | { kind: 'person'; id: number; title: string }

const SIZE_KEY = 'sf-chat-size'
const MIN = { w: 300, h: 320 }
const MAX = { w: 640, h: 760 }
const DEFAULT_SIZE = { w: 368, h: 512 }

/** The round button in the corner, and the panel it opens.
 *
 *  Lives in the dashboard shell so chat follows the student across pages:
 *  the socket is already connected for notifications, and a conversation
 *  does not belong to whichever page happens to be open. */
export function ChatLauncher() {
  const t = useTranslations('notebooks')
  const [open, setOpen] = useState(false)
  const [overview, setOverview] = useState<ChatOverview | null>(null)
  const [conversation, setConversation] = useState<Open | null>(null)
  const [unread, setUnread] = useState(false)
  const [creating, setCreating] = useState(false)
  // The box is the student's to size; the choice is per browser.
  const [size, setSize] = useState(DEFAULT_SIZE)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(SIZE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved) as { w: number; h: number }
        setSize({
          w: Math.min(MAX.w, Math.max(MIN.w, parsed.w)),
          h: Math.min(MAX.h, Math.max(MIN.h, parsed.h)),
        })
      }
    } catch {
      /* no storage, or a value we cannot read: the default stands */
    }
  }, [])

  /** Drag the top-left corner. Pointer events rather than mouse events, so a
   *  trackpad, a mouse and a touch screen all resize the same way. */
  const startResize = (e: React.PointerEvent) => {
    e.preventDefault()
    const from = { x: e.clientX, y: e.clientY, ...size }
    const move = (ev: PointerEvent) => {
      const next = {
        w: Math.min(MAX.w, Math.max(MIN.w, from.w + (from.x - ev.clientX))),
        h: Math.min(MAX.h, Math.max(MIN.h, from.h + (from.y - ev.clientY))),
      }
      setSize(next)
    }
    const stop = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
      setSize((s) => {
        try {
          window.localStorage.setItem(SIZE_KEY, JSON.stringify(s))
        } catch {
          /* ignore */
        }
        return s
      })
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
  }

  const load = useCallback(() => {
    notebooksAPI
      .chatOverview()
      .then((res) => setOverview(res.data))
      .catch(() => setOverview({ groups: [], people: [] }))
  }, [])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  // A dot on the button when something arrives while the panel is shut.
  useEffect(() => {
    let socket: Socket | null = null
    let cancelled = false
    const ping = () => {
      if (!open) setUnread(true)
      if (open) load()
    }
    void getSocket().then((s) => {
      if (cancelled || !s) return
      socket = s
      s.on('message:new', ping)
      s.on('direct:new', ping)
    })
    return () => {
      cancelled = true
      socket?.off('message:new', ping)
      socket?.off('direct:new', ping)
    }
  }, [open, load])

  // Escape closes, and closing returns focus to the button.
  const buttonRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const openPanel = () => {
    setUnread(false)
    setOpen((v) => !v)
  }

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={openPanel}
        aria-expanded={open}
        aria-label={open ? t('chatClose') : t('chatOpen')}
        className={cn(
          'fixed bottom-5 right-5 z-40 grid size-14 place-items-center rounded-full text-white shadow-lift',
          'bg-slate-900 transition-[transform,background-color] duration-150 hover:bg-slate-800',
          'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-slate-400/40',
          'active:scale-95 motion-reduce:transition-none motion-reduce:active:scale-100',
        )}
      >
        {open ? <X className="size-6" aria-hidden /> : <MessageCircle className="size-6" aria-hidden />}
        {unread && !open && (
          <span
            className="absolute right-3 top-3 size-2.5 rounded-full bg-mode-flashcards ring-2 ring-white"
            aria-hidden
          />
        )}
        {unread && !open && <span className="sr-only">•</span>}
      </button>

      {open && (
        <div
          ref={panelRef}
          role="dialog"
          aria-label={t('chatHeading')}
          style={{ ['--chat-w' as string]: `${size.w}px`, ['--chat-h' as string]: `${size.h}px` }}
          className={cn(
            'chat-panel fixed z-40 flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lift',
            'inset-x-3 bottom-24 top-16',
            'sm:inset-x-auto sm:top-auto sm:bottom-24 sm:right-5 sm:h-[var(--chat-h)] sm:w-[var(--chat-w)]',
          )}
        >
          {/* Drag the corner nearest the middle of the screen: the panel is
              anchored bottom-right, so it grows up and to the left. */}
          <button
            type="button"
            onPointerDown={startResize}
            aria-label={t('chatResize')}
            className="absolute left-0 top-0 z-10 hidden size-5 cursor-nwse-resize items-center justify-center rounded-br-lg text-slate-400 hover:text-slate-700 sm:flex"
          >
            <svg viewBox="0 0 10 10" className="size-3" aria-hidden>
              <path d="M9 1 1 9M5 1 1 5" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" />
            </svg>
          </button>
          <header className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
            {conversation ? (
              <>
                <button
                  type="button"
                  onClick={() => setConversation(null)}
                  aria-label={t('chatBack')}
                  className="-ml-1 rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                >
                  <ChevronLeft className="size-5" aria-hidden />
                </button>
                <h2 className="min-w-0 flex-1 truncate text-base font-semibold text-slate-900">
                  {conversation.title}
                </h2>
              </>
            ) : (
              <>
                <h2 className="flex-1 text-base font-semibold text-slate-900">{t('chatHeading')}</h2>
                <button
                  type="button"
                  onClick={() => setCreating((v) => !v)}
                  aria-pressed={creating}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-sm font-medium text-mode-library hover:bg-slate-100"
                >
                  <Plus className="size-4" aria-hidden />
                  {t('chatNewGroup')}
                </button>
              </>
            )}
          </header>

          {conversation ? (
            <div className="flex min-h-0 flex-1 flex-col p-3">
              {conversation.kind === 'group' ? (
                <GroupChat groupId={conversation.id} />
              ) : (
                <DirectChat userId={conversation.id} />
              )}
            </div>
          ) : creating ? (
            <NewGroupForm
              people={overview?.people ?? []}
              onCancel={() => setCreating(false)}
              onCreated={(g) => {
                setCreating(false)
                load()
                setConversation({ kind: 'group', id: g.id, title: g.name })
              }}
            />
          ) : (
            <ConversationList
              overview={overview}
              onPick={setConversation}
              emptyLabel={t('chatNoConversations')}
            />
          )}
        </div>
      )}
    </>
  )
}

function ConversationList({
  overview,
  onPick,
  emptyLabel,
}: {
  overview: ChatOverview | null
  onPick: (c: Open) => void
  emptyLabel: string
}) {
  const t = useTranslations('notebooks')
  if (overview === null) {
    return (
      <div className="space-y-2 p-3" aria-busy>
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none" />
        ))}
      </div>
    )
  }
  if (overview.groups.length === 0 && overview.people.length === 0) {
    return <p className="p-6 text-center text-sm text-slate-600">{emptyLabel}</p>
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <Section label={t('chatGroups')}>
        {overview.groups.map((g) => (
          <Row
            key={`g${g.id}`}
            icon={<Users className="size-4 text-mode-library" aria-hidden />}
            title={g.name}
            subtitle={g.last ? lastLine(g.last) : t('chatGroupMembers', { count: g.members })}
            onClick={() => onPick({ kind: 'group', id: g.id, title: g.name })}
          />
        ))}
      </Section>
      {overview.people.length > 0 && (
        <Section label={t('chatPeople')}>
          {overview.people.map((p) => (
            <Row
              key={`p${p.user_id}`}
              icon={<UserRound className="size-4 text-slate-500" aria-hidden />}
              title={p.name}
              subtitle={p.last ? lastLine(p.last) : t('chatNoLast')}
              onClick={() => onPick({ kind: 'person', id: p.user_id, title: p.name })}
            />
          ))}
        </Section>
      )}
    </div>
  )
}

function lastLine(last: ChatLastLine): string {
  const who = last.is_you ? '' : `${last.author}: `
  return `${who}${last.body}`
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-slate-100 last:border-b-0">
      <h3 className="px-4 pb-1 pt-3 text-xs font-semibold text-slate-500">{label}</h3>
      <ul>{children}</ul>
    </section>
  )
}

function Row({
  icon,
  title,
  subtitle,
  onClick,
}: {
  icon: React.ReactNode
  title: string
  subtitle: string
  onClick: () => void
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-slate-50 focus-visible:bg-slate-50 focus-visible:outline-none"
      >
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-slate-100">{icon}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-medium text-slate-900">{title}</span>
          <span className="block truncate text-sm text-slate-600">{subtitle}</span>
        </span>
      </button>
    </li>
  )
}

/** Naming a group and choosing who is in it. The candidates are the people
 *  you already share study material with, which is also what the server
 *  enforces — the list cannot offer a stranger. */
function NewGroupForm({
  people,
  onCancel,
  onCreated,
}: {
  people: { user_id: number; name: string }[]
  onCancel: () => void
  onCreated: (group: { id: number; name: string }) => void
}) {
  const t = useTranslations('notebooks')
  const common = useTranslations('common')
  const [name, setName] = useState('')
  const [picked, setPicked] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const toggle = (id: number) =>
    setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      const res = await notebooksAPI.createGroup({ name: name.trim(), members: picked })
      onCreated(res.data)
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail || t('chatCreateFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col gap-3 p-4">
      <label className="space-y-1.5">
        <span className="text-sm font-medium text-slate-900">{t('chatGroupName')}</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('chatGroupNamePlaceholder')}
          maxLength={120}
          autoFocus
          className="h-10 w-full rounded-lg border border-slate-300 px-3 text-base text-slate-900 outline-none focus-visible:border-mode focus-visible:ring-[3px] focus-visible:ring-mode/25"
        />
      </label>

      <p className="text-sm font-medium text-slate-900">{t('chatPickPeople')}</p>
      {people.length === 0 ? (
        <p className="text-sm text-slate-600">{t('chatNoPeople')}</p>
      ) : (
        <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto">
          {people.map((p) => (
            <li key={p.user_id}>
              <label className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-slate-50">
                <input
                  type="checkbox"
                  checked={picked.includes(p.user_id)}
                  onChange={() => toggle(p.user_id)}
                  className="size-4 rounded border-slate-300 accent-[var(--mode)]"
                />
                <span className="text-[15px] text-slate-900">{p.name}</span>
              </label>
            </li>
          ))}
        </ul>
      )}

      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}

      <div className="mt-auto flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          {common('cancel')}
        </Button>
        <Button type="submit" size="sm" disabled={busy || !name.trim()}>
          {t('chatCreate')}
        </Button>
      </div>
    </form>
  )
}
