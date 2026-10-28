'use client'

import { use, useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Check, ChevronLeft, Loader2, LogOut, Users, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MathText } from '@/components/math-text'
import { PageHeader } from '@/components/page-header'
import { liveAPI } from '@/lib/api'
import { applyBroadcast, optionShares, secondsLeft, type LiveBroadcast, type LiveState } from '@/lib/live'
import { getSocket } from '@/lib/realtime'
import { cn } from '@/lib/utils'

const LETTERS = 'ABCDEFGH'

/** One live round. The server owns it: this page shows what it last heard,
 *  counts down against the server's remaining time, and asks for the reveal
 *  when its own countdown runs out (the server checks the clock again). */
export default function LiveRoomPage({ params }: { params: Promise<{ roomId: string }> }) {
  const { roomId } = use(params)
  const id = Number(roomId)
  const t = useTranslations('live')
  const router = useRouter()
  const [room, setRoom] = useState<LiveState | null>(null)
  const [missing, setMissing] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // When the last state arrived, so remaining_ms and next_open_ms become clock times here.
  const [receivedAt, setReceivedAt] = useState(() => Date.now())
  const [now, setNow] = useState(() => Date.now())
  const askedReveal = useRef<number | null>(null)

  const take = useCallback((next: LiveState) => {
    setRoom(next)
    setReceivedAt(Date.now())
  }, [])

  const refresh = useCallback(() => {
    liveAPI.get(id).then((res) => take(res.data)).catch(() => setMissing(true))
  }, [id, take])

  const validId = Number.isFinite(id) && id > 0

  useEffect(() => {
    if (validId) refresh()
  }, [validId, refresh])

  // Changes arrive over the socket; a reconnect re-joins the room and refetches.
  useEffect(() => {
    let cancelled = false
    let off = () => {}
    void getSocket().then((s) => {
      if (cancelled || !s) return
      const join = () => s.emit('live:join', { room: id })
      const onState = (payload: LiveBroadcast) => {
        if (payload.id !== id) return
        setRoom((prev) => (prev ? applyBroadcast(prev, payload) : prev))
        setReceivedAt(Date.now())
        // My own seat (my answer, my misses) only comes with a fetch.
        if (payload.status === 'finished') refresh()
      }
      join()
      s.on('connect', join)
      s.on('connect', refresh)
      s.on('live:state', onState)
      off = () => {
        s.emit('live:leave', { room: id })
        s.off('connect', join)
        s.off('connect', refresh)
        s.off('live:state', onState)
      }
    })
    return () => {
      cancelled = true
      off()
    }
  }, [id, refresh])

  useEffect(() => {
    if (!room || (room.status !== 'question' && room.status !== 'reveal')) return
    const timer = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(timer)
  }, [room?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const deadline = receivedAt + (room?.remaining_ms ?? 0)
  const nextOpenAt = receivedAt + (room?.next_open_ms ?? 0)

  // Time up here: ask for the reveal once per question. Harmless if the
  // server's clock says otherwise; it answers with the state as it is.
  useEffect(() => {
    if (!room || room.status !== 'question' || now < deadline + 300) return
    if (askedReveal.current === room.index) return
    askedReveal.current = room.index
    liveAPI.reveal(id).then((res) => take(res.data)).catch(() => {})
  }, [room, now, deadline, id, take])

  const act = async (name: string, call: () => Promise<{ data: LiveState }>) => {
    if (busy) return
    setBusy(name)
    setError(null)
    try {
      take((await call()).data)
    } catch (e) {
      const status = (e as { response?: { status?: number } }).response?.status
      setError(status === 409 ? t('tooLate') : status === 403 ? t('notYours') : t('failed'))
      refresh()
    } finally {
      setBusy(null)
    }
  }

  const leave = async () => {
    try {
      await liveAPI.leave(id)
    } catch {
      /* leaving a room that has closed is still leaving */
    }
    router.push(room ? `/dashboard/notebooks/${room.notebook.id}` : '/dashboard')
  }

  if (missing || !validId) {
    return (
      <div className="mx-auto max-w-3xl space-y-8">
        <PageHeader title={t('title')} />
        <p className="sheet p-8 text-lg text-slate-700">{t('notFound')}</p>
      </div>
    )
  }
  if (!room) {
    return (
      <div className="mx-auto max-w-3xl space-y-8">
        <PageHeader title={t('title')} />
        <div className="sheet h-72 animate-pulse motion-reduce:animate-none" aria-busy />
      </div>
    )
  }

  const open = room.status !== 'finished'
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title={t('title')}
        meta={room.status === 'lobby' || room.status === 'finished'
          ? t('meta', { count: room.total, seconds: room.seconds })
          : t('progress', { n: room.index + 1, total: room.total })}
        lead={<Link href={`/dashboard/notebooks/${room.notebook.id}`} className="underline-offset-4 hover:underline">{room.notebook.title}</Link>}
        action={open && room.you.joined ? (
          <Button variant="outline" onClick={() => void leave()}>
            <LogOut aria-hidden />
            {t('leave')}
          </Button>
        ) : (
          <Button asChild variant="outline">
            <Link href={`/dashboard/notebooks/${room.notebook.id}`}>
              <ChevronLeft aria-hidden />
              {t('backToNotebook')}
            </Link>
          </Button>
        )}
      />

      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}

      {open && !room.you.joined ? (
        <section className="sheet flex flex-wrap items-center justify-between gap-4 p-6 md:p-8">
          <p className="max-w-[48ch] text-base text-slate-800">{t('notJoined', { host: room.host.name })}</p>
          <Button onClick={() => void act('join', () => liveAPI.join(id))} disabled={busy !== null}>
            {busy === 'join' && <Loader2 className="animate-spin" aria-hidden />}
            {t('join')}
          </Button>
        </section>
      ) : room.status === 'lobby' ? (
        <Lobby room={room} busy={busy} onStart={() => void act('start', () => liveAPI.start(id))} />
      ) : room.status === 'question' ? (
        <Question
          room={room}
          secondsLeft={secondsLeft(deadline, now)}
          share={Math.max(0, Math.min(1, (deadline - now) / (room.seconds * 1000)))}
          busy={busy}
          onAnswer={(choice) => void act('answer', () => liveAPI.answer(id, room.index, choice))}
        />
      ) : room.status === 'reveal' ? (
        <Reveal
          room={room}
          waitSeconds={room.you.is_host ? 0 : secondsLeft(nextOpenAt, now)}
          busy={busy}
          onNext={() => void act('next', () => liveAPI.next(id, room.index))}
        />
      ) : (
        <Finished room={room} />
      )}

      {open && room.you.joined && <Players room={room} />}
    </div>
  )
}

function Lobby({ room, busy, onStart }: { room: LiveState; busy: string | null; onStart: () => void }) {
  const t = useTranslations('live')
  return (
    <section className="sheet p-6 md:p-8" aria-live="polite">
      <h2 className="font-display text-xl font-semibold text-slate-900">{t('lobbyTitle')}</h2>
      <p className="mt-2 max-w-[60ch] text-base leading-relaxed text-slate-700">{t('lobbyLead')}</p>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        <p className="text-base text-slate-800">{t('waiting', { count: room.players.length })}</p>
        {room.you.is_host ? (
          <Button size="lg" onClick={onStart} disabled={busy !== null}>
            {busy === 'start' && <Loader2 className="animate-spin" aria-hidden />}
            {t('start')}
          </Button>
        ) : (
          <p className="text-base text-slate-700">{t('hostStarts', { host: room.host.name })}</p>
        )}
      </div>
    </section>
  )
}

function Question({ room, secondsLeft: left, share, busy, onAnswer }: {
  room: LiveState
  secondsLeft: number
  share: number
  busy: string | null
  onAnswer: (choice: string) => void
}) {
  const t = useTranslations('live')
  const q = room.question
  if (!q) return null
  const mine = room.you.answer
  const waitingFor = room.players.length - room.answered_count
  return (
    <section className="sheet overflow-hidden" aria-labelledby="live-question">
      {/* The countdown: a bar that empties, and the number for anyone who cannot see the bar. */}
      <div className="h-1.5 bg-slate-100" aria-hidden>
        <div
          className={cn('h-full transition-[width] duration-300 ease-linear motion-reduce:transition-none', left <= 5 ? 'bg-red-600' : 'bg-mode')}
          style={{ width: `${share * 100}%` }}
        />
      </div>
      <div className="p-6 md:p-8">
        <div className="flex items-center justify-between gap-4 text-sm">
          <span className="font-medium text-mode-ink">{t('question', { n: room.index + 1 })}</span>
          <span className={cn('font-mono tabular-nums', left <= 5 ? 'text-red-700' : 'text-slate-700')} aria-live="off">
            {t('secondsLeft', { s: left })}
          </span>
        </div>
        <p id="live-question" className="mt-3 max-w-[65ch] text-xl leading-relaxed text-slate-900 text-pretty">
          <MathText text={q.text} />
        </p>
        <ul className="mt-6 grid gap-3 sm:grid-cols-2">
          {q.options.map((option, i) => {
            const chosen = mine === option
            return (
              <li key={option}>
                <button
                  type="button"
                  onClick={() => onAnswer(option)}
                  disabled={mine !== null || busy !== null || left === 0}
                  aria-pressed={chosen}
                  className={cn(
                    'flex min-h-14 w-full items-start gap-3 rounded-lg border px-4 py-3 text-left text-base leading-relaxed transition-colors duration-150 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 motion-reduce:transition-none',
                    chosen ? 'border-mode bg-mode/10 text-slate-900' : 'border-slate-300 bg-white text-slate-900',
                    mine === null && 'hover:border-mode hover:bg-mode/5',
                    mine !== null && !chosen && 'border-slate-200 text-slate-700'
                  )}
                >
                  <span className={cn('mt-0.5 grid size-6 shrink-0 place-items-center rounded font-mono text-sm', chosen ? 'bg-mode-strong text-mode-on' : 'bg-slate-100 text-slate-700')}>
                    {LETTERS[i]}
                  </span>
                  <span className="min-w-0"><MathText text={option} /></span>
                </button>
              </li>
            )
          })}
        </ul>
        <p className="mt-5 text-sm text-slate-700" aria-live="polite">
          {mine === null ? t('answerOnce') : waitingFor > 0 ? t('answeredWaiting', { count: waitingFor }) : t('answeredAll')}
        </p>
      </div>
    </section>
  )
}

function Reveal({ room, waitSeconds, busy, onNext }: {
  room: LiveState
  waitSeconds: number
  busy: string | null
  onNext: () => void
}) {
  const t = useTranslations('live')
  const q = room.question
  const r = room.reveal
  if (!q || !r) return null
  const mine = room.you.answer
  const names = new Map(room.players.map((p) => [p.user_id, p.name]))
  const right = r.right.map((uid) => names.get(uid)).filter(Boolean)
  const last = room.index + 1 >= room.total
  return (
    <section className="sheet divide-y divide-slate-200" aria-live="polite" aria-labelledby="live-reveal">
      <div className="p-6 md:p-8">
        <p className="text-sm font-medium text-mode-ink">{t('question', { n: room.index + 1 })}</p>
        <p id="live-reveal" className="mt-3 max-w-[65ch] text-xl leading-relaxed text-slate-900 text-pretty">
          <MathText text={q.text} />
        </p>
        <p className={cn('mt-4 flex items-center gap-2 text-base font-medium', mine === r.correct ? 'text-emerald-800' : 'text-red-800')}>
          {mine === r.correct ? <Check className="size-5" aria-hidden /> : <X className="size-5" aria-hidden />}
          {mine === null ? t('noAnswer') : mine === r.correct ? t('youRight') : t('youWrong')}
        </p>
        {/* How the room split: the discussion starts from here. */}
        <ul className="mt-5 space-y-2.5" aria-label={t('splitLabel')}>
          {optionShares(r.counts, q.options).map(({ option, n, share }, i) => {
            const correct = option === r.correct
            return (
              <li key={option} className={cn('rounded-lg border px-4 py-3', correct ? 'border-emerald-600 bg-emerald-50' : 'border-slate-200 bg-white')}>
                <div className="flex items-start gap-3 text-base">
                  <span className={cn('mt-0.5 grid size-6 shrink-0 place-items-center rounded font-mono text-sm', correct ? 'bg-emerald-700 text-white' : 'bg-slate-100 text-slate-700')}>
                    {LETTERS[i]}
                  </span>
                  <span className="min-w-0 flex-1 text-slate-900"><MathText text={option} /></span>
                  <span className={cn('shrink-0 font-mono text-sm tabular-nums', correct ? 'text-emerald-900' : 'text-slate-700')}>
                    {t('picked', { count: n })}
                    {option === mine && <span className={cn('ml-1', correct ? 'text-emerald-950' : 'text-slate-900')}>· {t('you')}</span>}
                  </span>
                </div>
                <div className="mt-2 h-1.5 rounded-full bg-slate-100" aria-hidden>
                  <div className={cn('h-full rounded-full', correct ? 'bg-emerald-600' : 'bg-slate-400')} style={{ width: `${share * 100}%` }} />
                </div>
              </li>
            )
          })}
        </ul>
        <p className="mt-4 text-sm text-slate-700">
          {right.length ? t('gotItRight', { names: right.join(', ') }) : t('nobodyRight')}
        </p>
      </div>

      {(r.explanation || r.source_excerpt) && (
        <div className="space-y-3 p-6 md:p-8">
          {r.explanation && (
            <p className="max-w-[65ch] text-base leading-relaxed text-slate-800"><MathText text={r.explanation} /></p>
          )}
          {r.source_excerpt && (
            <figure className="max-w-[65ch] rounded-lg bg-slate-50 px-4 py-3">
              <figcaption className="text-sm font-medium text-slate-700">{t('fromSource', { title: r.source_title || '—' })}</figcaption>
              <blockquote className="mt-1 text-base leading-relaxed text-slate-800">“{r.source_excerpt}”</blockquote>
            </figure>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 p-6 md:p-8">
        <p className="max-w-[60ch] text-sm text-slate-700">
          {room.you.is_host ? t('talkFirst') : waitSeconds > 0 ? t('hostMovesOn', { host: room.host.name, s: waitSeconds }) : t('anyoneMovesOn')}
        </p>
        <Button onClick={onNext} disabled={busy !== null || waitSeconds > 0}>
          {busy === 'next' && <Loader2 className="animate-spin" aria-hidden />}
          {last ? t('seeResults') : t('next')}
        </Button>
      </div>
    </section>
  )
}

function Finished({ room }: { room: LiveState }) {
  const t = useTranslations('live')
  const missed = room.you.missed
  return (
    <>
      <section className="sheet p-6 md:p-8" aria-labelledby="live-results">
        <h2 id="live-results" className="font-display text-xl font-semibold text-slate-900">{t('resultsTitle')}</h2>
        <ol className="mt-4 divide-y divide-slate-200">
          {room.results.map((r) => (
            <li key={r.user_id} className={cn('flex items-center gap-4 py-3', r.user_id === room.you.user_id && 'font-semibold')}>
              <span className="w-6 font-mono text-sm tabular-nums text-slate-600">{r.rank}</span>
              <span className="min-w-0 flex-1 truncate text-base text-slate-900">
                {r.name}
                {r.user_id === room.you.user_id && <span className="ml-1 font-normal text-slate-600">({t('you')})</span>}
              </span>
              <span className="font-mono text-sm tabular-nums text-slate-800">{t('score', { score: r.score, total: room.total })}</span>
              <span className="hidden w-20 whitespace-nowrap text-right font-mono text-sm tabular-nums text-slate-600 sm:inline">{t('time', { s: Math.round(r.ms / 1000) })}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="sheet p-6 md:p-8" aria-labelledby="live-missed">
        <h2 id="live-missed" className="text-base font-semibold text-slate-900">
          {missed.length ? t('missedTitle', { count: missed.length }) : t('noneMissed')}
        </h2>
        {missed.length > 0 && (
          <>
            <p className="mt-1 max-w-[60ch] text-sm text-slate-700">{t('missedNote')}</p>
            <ul className="mt-4 space-y-4">
              {missed.map((m) => (
                <li key={m.question_id} className="max-w-[65ch] space-y-1.5">
                  <p className="text-base leading-relaxed text-slate-900"><MathText text={m.text} /></p>
                  <p className="text-sm text-slate-700">
                    {m.your_answer ? <>{t('yourAnswer')}: <span className="text-red-800"><MathText text={m.your_answer} /></span> · </> : <>{t('noAnswer')} · </>}
                    {t('rightAnswer')}: <span className="text-emerald-800"><MathText text={m.correct} /></span>
                  </p>
                  {m.explanation && <p className="text-sm leading-relaxed text-slate-700"><MathText text={m.explanation} /></p>}
                </li>
              ))}
            </ul>
          </>
        )}
        <div className="mt-6 flex flex-wrap gap-2">
          <Button asChild>
            <Link href={`/dashboard/notebooks/${room.notebook.id}`}>{t('backToNotebook')}</Link>
          </Button>
        </div>
      </section>
    </>
  )
}

function Players({ room }: { room: LiveState }) {
  const t = useTranslations('live')
  const showAnswered = room.status === 'question'
  return (
    <section className="sheet p-5 md:px-8" aria-labelledby="live-players">
      <h2 id="live-players" className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <Users className="size-4 text-slate-600" aria-hidden />
        {t('players', { count: room.players.length })}
      </h2>
      <ul className="mt-3 flex flex-wrap gap-2">
        {room.players.map((p) => (
          <li
            key={p.user_id}
            className={cn('flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm',
              showAnswered && p.answered ? 'border-mode/50 bg-mode/10 text-slate-900' : 'border-slate-200 bg-white text-slate-800')}
          >
            {showAnswered && p.answered && <Check className="size-3.5 text-mode-ink" aria-label={t('hasAnswered')} />}
            <span>{p.name}</span>
            {p.user_id === room.host.user_id && <span className="text-slate-600">· {t('host')}</span>}
            {room.status !== 'lobby' && <span className="font-mono tabular-nums text-slate-700">{p.score}</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}
