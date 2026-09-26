'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronLeft, MessageCircle, NotebookText, UserRound, X } from 'lucide-react'
import type { Socket } from 'socket.io-client'
import { notebooksAPI, type ChatLastLine, type ChatOverview } from '@/lib/api'
import { getSocket } from '@/lib/realtime'
import { NotebookChat } from '@/components/notebook-chat'
import { DirectChat } from '@/components/direct-chat'
import { cn } from '@/lib/utils'

type Open = { kind: 'group'; id: number; title: string } | { kind: 'person'; id: number; title: string }

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
  const panelRef = useRef<HTMLDivElement>(null)

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
          className={cn(
            'chat-panel fixed z-40 flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lift',
            'inset-x-3 bottom-24 top-16 sm:inset-x-auto sm:top-auto sm:bottom-24 sm:right-5 sm:h-[32rem] sm:w-[23rem]',
          )}
        >
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
              <h2 className="flex-1 text-base font-semibold text-slate-900">{t('chatHeading')}</h2>
            )}
          </header>

          {conversation ? (
            <div className="flex min-h-0 flex-1 flex-col p-3">
              {conversation.kind === 'group' ? (
                <NotebookChat notebookId={conversation.id} />
              ) : (
                <DirectChat userId={conversation.id} />
              )}
            </div>
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
            key={`g${g.notebook}`}
            icon={<NotebookText className="size-4 text-mode-library" aria-hidden />}
            title={g.title}
            subtitle={g.last ? lastLine(g.last) : t('chatGroupMembers', { count: g.members })}
            onClick={() => onPick({ kind: 'group', id: g.notebook, title: g.title })}
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
