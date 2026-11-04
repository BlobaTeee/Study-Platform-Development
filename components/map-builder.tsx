'use client'

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { ArrowLeft, Check, FileText, Loader2, Plus, RotateCcw, Trash2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { notebooksAPI } from '@/lib/api'
import {
  MAX_CARDS, MAX_LABEL, addCard, addLink, blocker, freeSpot, pairId, removeCard, removeLink, tally,
  type BuildLink, type BuildResult, type Card, type Verdict,
} from '@/lib/map-build'
import { cn } from '@/lib/utils'

type Topic = { source_id: number; title: string; key_points: number }
type Selected = { kind: 'card'; id: string } | { kind: 'link'; id: string } | null

const CARD = { w: 150, h: 56, gapX: 72, gapY: 96 }
const DRAG_SLOP = 4

// Verdict colours follow the map's mastery colours: emerald right, amber
// partly, red wrong; slate for what the model left out.
const LINE: Record<Verdict, string> = {
  correct: 'stroke-emerald-600',
  partial: 'stroke-amber-500',
  wrong: 'stroke-red-500',
  unjudged: 'stroke-slate-400',
}
const BADGE: Record<Verdict, string> = {
  correct: 'bg-emerald-50 text-emerald-900 ring-emerald-600/40',
  partial: 'bg-amber-50 text-amber-900 ring-amber-500/50',
  wrong: 'bg-red-50 text-red-800 ring-red-500/40',
  unjudged: 'bg-slate-100 text-slate-700 ring-slate-400/40',
}

const draftKey = (notebookId: number, sourceId: number) => `map-draft:${notebookId}:${sourceId}`

function loadDraft(key: string): { cards: Card[]; links: BuildLink[] } {
  try {
    const raw = JSON.parse(localStorage.getItem(key) ?? 'null')
    if (raw && Array.isArray(raw.cards) && Array.isArray(raw.links)) return raw
  } catch {
    /* private mode or a broken draft: start empty */
  }
  return { cards: [], links: [] }
}

/** Build a map of one document from memory: write the concepts you remember
 *  as cards, drag them where you like, press one card then another to link
 *  them and say why next to the line. One request then compares the map with
 *  the document: what was recalled, what was missed, and each link judged. */
export function MapBuilder({ notebookId, onClose }: { notebookId: number; onClose: () => void }) {
  const t = useTranslations('map')
  const [topics, setTopics] = useState<Topic[] | null>(null)
  const [topic, setTopic] = useState<Topic | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    notebooksAPI
      .mapTopics(notebookId)
      .then((res) => {
        if (!cancelled) setTopics(res.data.topics)
      })
      .catch(() => {
        if (!cancelled) setError('')
      })
    return () => {
      cancelled = true
    }
  }, [notebookId])

  return (
    <div className="sheet overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 md:px-5">
        <div className="min-w-0">
          <h2 className="font-display text-lg font-semibold text-slate-900">{t('buildTitle')}</h2>
          {topic && (
            <p className="flex flex-wrap items-center gap-x-2 text-sm text-slate-700">
              <FileText className="size-3.5 text-slate-500" aria-hidden />
              <span className="truncate">{topic.title}</span>
              <button
                type="button"
                onClick={() => setTopic(null)}
                className="rounded text-mode-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
              >
                {t('buildChangeTopic')}
              </button>
            </p>
          )}
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          <ArrowLeft aria-hidden />
          {t('buildBack')}
        </Button>
      </div>

      {topic ? (
        <Builder key={topic.source_id} notebookId={notebookId} topic={topic} onClose={onClose} />
      ) : error !== null ? (
        <p role="alert" className="px-5 py-6 text-base text-red-700">{t('failed')}</p>
      ) : !topics ? (
        <div className="flex h-48 items-center justify-center" aria-busy>
          <Loader2 className="size-5 animate-spin text-mode motion-reduce:animate-none" aria-hidden />
        </div>
      ) : topics.length === 0 ? (
        <p className="max-w-prose px-5 py-6 text-base leading-relaxed text-slate-700">{t('buildNoTopics')}</p>
      ) : (
        <div className="space-y-3 p-4 md:p-5">
          <p className="max-w-prose text-base leading-relaxed text-slate-800">{t('buildPickTopic')}</p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {topics.map((tp) => (
              <li key={tp.source_id}>
                <button
                  type="button"
                  onClick={() => setTopic(tp)}
                  className="flex w-full items-center gap-3 rounded-lg border border-slate-300 bg-white px-4 py-3 text-left hover:border-mode hover:bg-mode/5 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                >
                  <FileText className="size-4 shrink-0 text-mode-ink" aria-hidden />
                  <span className="min-w-0 flex-1 truncate text-base font-medium text-slate-900">{tp.title}</span>
                  <span className="shrink-0 text-xs text-slate-600">{t('buildTopicPoints', { count: tp.key_points })}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Builder({ notebookId, topic, onClose }: { notebookId: number; topic: Topic; onClose: () => void }) {
  const t = useTranslations('map')
  const key = draftKey(notebookId, topic.source_id)
  const [{ cards, links }, setMap] = useState(() => loadDraft(key))
  const [selected, setSelected] = useState<Selected>(null)
  const [linkFrom, setLinkFrom] = useState<string | null>(null)
  const [label, setLabel] = useState('')
  const [result, setResult] = useState<BuildResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canvas = useRef<HTMLDivElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const [sizes, setSizes] = useState<Record<string, { w: number; h: number }>>({})
  const [width, setWidth] = useState(600)
  const [height, setHeight] = useState(440)
  // The canvas grows past the visible width when cards lie further right (a map
  // made on a wide screen, opened on a phone): it scrolls instead of cutting them off.
  const [extent, setExtent] = useState(600)
  // A link just made opens with its reason box focused, once.
  const [fresh, setFresh] = useState<string | null>(null)

  // The work in progress stays in this browser until it is compared.
  useEffect(() => {
    if (result) return
    try {
      localStorage.setItem(key, JSON.stringify({ cards, links }))
    } catch {
      /* private mode: nothing kept */
    }
  }, [key, cards, links, result])

  // Card sizes (a long name wraps) and the canvas size, for lines and placing.
  useLayoutEffect(() => {
    const el = canvas.current
    const view = scroller.current
    if (!el || !view) return
    const measure = () => {
      setWidth(view.clientWidth)
      const next: Record<string, { w: number; h: number }> = {}
      el.querySelectorAll<HTMLElement>('[data-card]').forEach((c) => {
        next[c.dataset.card!] = { w: c.offsetWidth, h: c.offsetHeight }
      })
      setSizes(next)
      const bottom = Math.max(0, ...cards.map((c) => c.y + (next[c.id]?.h ?? CARD.h)))
      setHeight(Math.max(440, bottom + 80))
      const right = Math.max(0, ...cards.map((c) => c.x + (next[c.id]?.w ?? CARD.w)))
      setExtent(Math.max(view.clientWidth, right + 24))
    }
    measure()
    const watch = new ResizeObserver(measure)
    watch.observe(view)
    return () => watch.disconnect()
  }, [cards])

  const centre = (id: string) => {
    const c = cards.find((x) => x.id === id)
    const s = sizes[id] ?? { w: CARD.w, h: CARD.h }
    return c ? { x: c.x + s.w / 2, y: c.y + s.h / 2 } : null
  }
  const labelOf = (id: string) => cards.find((c) => c.id === id)?.label ?? ''

  const add = () => {
    if (result) return
    const spot = freeSpot(cards, width, CARD)
    const id = `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
    setMap((m) => ({ ...m, cards: addCard(m.cards, label, id, spot) }))
    setLabel('')
  }

  const press = (id: string) => {
    if (result) return setSelected({ kind: 'card', id })
    if (!linkFrom) {
      setLinkFrom(id)
      setSelected({ kind: 'card', id })
      return
    }
    if (linkFrom === id) {
      setLinkFrom(null)
      setSelected(null)
      return
    }
    const made = addLink(links, linkFrom, id)
    if (made !== links) {
      setMap((m) => ({ ...m, links: made }))
      setFresh(pairId(linkFrom, id))
    }
    setSelected({ kind: 'link', id: pairId(linkFrom, id) })
    setLinkFrom(null)
  }

  const move = (id: string, x: number, y: number) =>
    setMap((m) => ({
      ...m,
      cards: m.cards.map((c) =>
        c.id === id ? { ...c, x: Math.max(0, Math.min(x, extent - (sizes[id]?.w ?? CARD.w))), y: Math.max(0, y) } : c),
    }))

  const drop = (id: string) => {
    setMap((m) => removeCard(m.cards, m.links, id))
    setSelected(null)
    setLinkFrom(null)
  }

  const send = async () => {
    if (blocker(cards, links) || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await notebooksAPI.mapBuild(notebookId, {
        source: topic.source_id,
        cards: cards.map(({ id, label }) => ({ id, label })),
        links,
      })
      setResult(res.data)
      setSelected(null)
      setLinkFrom(null)
      try {
        localStorage.removeItem(key)
      } catch {
        /* nothing kept anyway */
      }
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      setError(typeof detail === 'string' ? detail : t('failed'))
    } finally {
      setBusy(false)
    }
  }

  const again = () => {
    setMap({ cards: [], links: [] })
    setResult(null)
    setSelected(null)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setLinkFrom(null)
      setSelected(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const shown = result ? result.links : links.map((x) => ({ ...x, verdict: null as Verdict | null, feedback: '' }))
  const number = new Map(shown.map((x, i) => [pairId(x.from, x.to), i + 1]))
  const focusOn = selected?.kind === 'card' ? selected.id : null
  const focusLink = selected?.kind === 'link' ? selected.id : null
  const lit = (x: { from: string; to: string }) =>
    focusLink ? pairId(x.from, x.to) === focusLink : focusOn ? x.from === focusOn || x.to === focusOn : true
  const matchOf = new Map(result?.cards.map((c) => [c.id, c.match_label]) ?? [])
  const stop = blocker(cards, links)
  const step = result ? 3 : cards.length < 3 ? 1 : 2
  const openLink = focusLink ? shown.find((x) => pairId(x.from, x.to) === focusLink) ?? null : null

  return (
    <div>
      <div className="space-y-3 border-b border-slate-200 px-4 py-3 md:px-5">
        <Steps current={step} />
        {!result && (
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              add()
            }}
          >
            <label htmlFor="new-concept" className="sr-only">{t('buildAddLabel')}</label>
            <input
              id="new-concept"
              value={label}
              maxLength={MAX_LABEL}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={t('buildAddPlaceholder')}
              autoComplete="off"
              autoFocus
              className="h-10 min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 placeholder:text-slate-500 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 sm:max-w-sm"
            />
            <Button type="submit" variant="outline" disabled={!label.trim() || cards.length >= MAX_CARDS}>
              <Plus aria-hidden />
              {t('buildAdd')}
            </Button>
          </form>
        )}
        <p className="text-sm text-slate-700" aria-live="polite">
          {result
            ? t('buildResultHint')
            : linkFrom
              ? t('buildPickSecond', { label: labelOf(linkFrom) })
              : cards.length === 0
                ? t('buildHintEmpty')
                : cards.length < 3
                  ? t('buildHintMore', { count: 3 - cards.length })
                  : t('buildHintLink')}
        </p>
      </div>

      {/* The canvas: lines under the cards, numbers on the lines, the open link's box beside it. */}
      <div ref={scroller} className="overflow-auto">
      <div
        ref={canvas}
        className="relative bg-[radial-gradient(circle,rgb(148_163_184/0.35)_1px,transparent_1px)] [background-size:20px_20px]"
        style={{ height, width: extent }}
        onPointerDown={(e) => {
          if (e.target === e.currentTarget) {
            setSelected(null)
            setLinkFrom(null)
          }
        }}
      >
        <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
          {result?.missed.map((m) => {
            const a = centre(m.from)
            const b = centre(m.to)
            return a && b && (
              <line key={`m-${pairId(m.from, m.to)}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                className="stroke-slate-400" strokeWidth={2} strokeDasharray="6 6" opacity={focusOn || focusLink ? 0.25 : 1} />
            )
          })}
          {shown.map((x) => {
            const a = centre(x.from)
            const b = centre(x.to)
            const on = lit(x)
            return a && b && (
              <line key={pairId(x.from, x.to)} x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeLinecap="round"
                strokeWidth={on && (focusLink || focusOn) ? 3.5 : 2.5}
                className={cn('transition-opacity duration-150', x.verdict ? LINE[x.verdict] : 'stroke-mode')}
                opacity={on ? 1 : 0.2} />
            )
          })}
        </svg>

        {cards.map((c) => (
          <CardBox
            key={c.id}
            card={c}
            picked={linkFrom === c.id || focusOn === c.id}
            faded={!!(focusOn || focusLink) && !(focusOn === c.id || (openLink && (openLink.from === c.id || openLink.to === c.id)) ||
              (focusOn && links.some((x) => (x.from === focusOn && x.to === c.id) || (x.to === focusOn && x.from === c.id))))}
            match={result ? (matchOf.get(c.id) ?? null) : undefined}
            locked={!!result}
            onPress={() => press(c.id)}
            onMove={(x, y) => move(c.id, x, y)}
            onDelete={() => drop(c.id)}
            deleteLabel={t('buildRemoveCard', { label: c.label })}
            notInDocument={t('buildNotInDocument')}
          />
        ))}

        {shown.map((x) => {
          const a = centre(x.from)
          const b = centre(x.to)
          if (!a || !b) return null
          const id = pairId(x.from, x.to)
          const n = number.get(id)!
          const empty = !result && x.why.trim().length < 3
          return (
            <button
              key={`n-${id}`}
              type="button"
              onClick={() => setSelected({ kind: 'link', id })}
              aria-label={t('buildOpenLink', { n, a: labelOf(x.from), b: labelOf(x.to) })}
              className={cn(
                'absolute z-20 grid size-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full font-mono text-xs font-semibold ring-2 transition-opacity',
                'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/50',
                x.verdict ? BADGE[x.verdict] : empty ? 'bg-amber-50 text-amber-900 ring-amber-500' : 'bg-white text-mode-ink ring-mode/60',
                !lit(x) && 'opacity-30',
              )}
              style={{ left: (a.x + b.x) / 2, top: (a.y + b.y) / 2 }}
            >
              {n}
            </button>
          )
        })}

        {openLink && (
          <LinkBox
            link={openLink}
            n={number.get(focusLink!)!}
            a={labelOf(openLink.from)}
            b={labelOf(openLink.to)}
            at={(() => {
              const a = centre(openLink.from)!
              const b = centre(openLink.to)!
              return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
            })()}
            width={extent}
            height={height}
            autoFocus={fresh === focusLink}
            onFocused={() => setFresh(null)}
            readOnly={!!result}
            onWhy={(why) => setMap((m) => ({
              ...m, links: m.links.map((y) => (pairId(y.from, y.to) === focusLink ? { ...y, why } : y)),
            }))}
            onDelete={() => {
              setMap((m) => ({ ...m, links: removeLink(m.links, openLink.from, openLink.to) }))
              setSelected(null)
            }}
            onClose={() => setSelected(null)}
          />
        )}
      </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3 md:px-5">
        {result ? (
          <>
            <p className="text-base font-semibold text-slate-900">
              {t('buildRecalled', { recalled: result.recalled, total: result.total })}
              <span className="ml-2 font-normal text-slate-700">
                · {t('buildScore', { correct: tally(result.links).correct, total: result.links.length })}
              </span>
            </p>
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={again}>
                <RotateCcw aria-hidden />
                {t('buildAgain')}
              </Button>
              <Button type="button" variant="outline" onClick={onClose}>{t('buildSeeMap')}</Button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-700">
              {t('buildCounts2', { cards: cards.length, links: links.length })}
              {stop && (
                <span className="ml-2 text-slate-600">
                  · {stop.kind === 'cards' ? t('buildNeedCards', { count: stop.need })
                    : stop.kind === 'links' ? t('buildNeedLinks') : t('buildNeedWhyN', { n: stop.n })}
                </span>
              )}
            </p>
            <Button type="button" onClick={() => void send()} disabled={busy || !!stop}>
              {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />}
              {busy ? t('buildSending') : t('buildSend')}
            </Button>
          </>
        )}
        {error && <p role="alert" className="basis-full text-sm text-red-700">{error}</p>}
      </div>

      {result && <Results result={result} labelOf={labelOf} onPick={(id) => setSelected({ kind: 'link', id })} />}
    </div>
  )
}

/** One of the student's cards: drag it anywhere; a press without moving picks it. */
function CardBox({ card, picked, faded, match, locked, onPress, onMove, onDelete, deleteLabel, notInDocument }: {
  card: Card
  picked: boolean
  faded: boolean
  /** After the comparison: the key point it matched, or null; undefined before. */
  match: string | null | undefined
  locked: boolean
  onPress: () => void
  onMove: (x: number, y: number) => void
  onDelete: () => void
  deleteLabel: string
  notInDocument: string
}) {
  const drag = useRef<{ px: number; py: number; x: number; y: number; moved: boolean } | null>(null)
  return (
    <div
      className={cn('group absolute z-10 w-[150px] transition-opacity duration-150', faded && 'opacity-40')}
      style={{ left: card.x, top: card.y }}
    >
      <button
        type="button"
        data-card={card.id}
        aria-pressed={picked}
        onPointerDown={(e) => {
          if (e.button !== 0) return
          drag.current = { px: e.clientX, py: e.clientY, x: card.x, y: card.y, moved: false }
          e.currentTarget.setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          const d = drag.current
          if (!d) return
          const dx = e.clientX - d.px
          const dy = e.clientY - d.py
          if (!d.moved && Math.hypot(dx, dy) < DRAG_SLOP) return
          d.moved = true
          onMove(d.x + dx, d.y + dy)
        }}
        onPointerUp={() => {
          const d = drag.current
          drag.current = null
          if (d && !d.moved) onPress()
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onPress()
            return
          }
          const step = e.shiftKey ? 40 : 12
          const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }
          const m = moves[e.key]
          if (m) {
            e.preventDefault()
            onMove(card.x + m[0], card.y + m[1])
          }
        }}
        className={cn(
          'relative w-full touch-none select-none rounded-lg border-2 bg-white px-3 py-2 text-left text-sm font-semibold leading-snug text-slate-900 shadow-sm',
          'cursor-grab active:cursor-grabbing focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/40',
          match === undefined
            ? picked ? 'border-mode ring-2 ring-mode/30' : 'border-slate-300 hover:border-mode/70'
            : match ? 'border-emerald-600' : 'border-dashed border-slate-400',
          picked && match !== undefined && 'ring-2 ring-mode/30',
        )}
      >
        {card.label}
        {match !== undefined && (
          <span className={cn('mt-1 block text-xs font-normal leading-snug', match ? 'text-emerald-800' : 'text-slate-600')}>
            {match ? `✓ ${match}` : notInDocument}
          </span>
        )}
      </button>
      {!locked && (
        <button
          type="button"
          onClick={onDelete}
          aria-label={deleteLabel}
          className="absolute -right-2 -top-2 grid size-6 place-items-center rounded-full border border-slate-300 bg-white text-slate-600 opacity-0 shadow-sm transition-opacity hover:text-red-700 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 group-hover:opacity-100"
        >
          <X className="size-3.5" aria-hidden />
        </button>
      )}
    </div>
  )
}

/** The open link's box, beside its number on the canvas: the reason to write,
 *  or, after the comparison, the verdict and the feedback. */
function LinkBox({ link, n, a, b, at, width, height, autoFocus, onFocused, readOnly, onWhy, onDelete, onClose }: {
  link: { from: string; to: string; why: string; verdict: Verdict | null; feedback: string }
  n: number
  a: string
  b: string
  at: { x: number; y: number }
  width: number
  height: number
  autoFocus: boolean
  onFocused: () => void
  readOnly: boolean
  onWhy: (why: string) => void
  onDelete: () => void
  onClose: () => void
}) {
  const t = useTranslations('map')
  const W = Math.min(280, width - 16)
  const left = Math.max(8, Math.min(at.x + 20, width - W - 8))
  const top = Math.max(8, Math.min(at.y + 20, height - 190))
  const box = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    if (autoFocus && box.current) {
      box.current.focus()
      onFocused()
    }
  }, [autoFocus, onFocused])
  return (
    <div
      role="dialog"
      aria-label={t('buildLinkLabel', { n, a, b })}
      className="absolute z-30 space-y-2 rounded-lg border border-slate-300 bg-white p-3 shadow-lg"
      style={{ left, top, width: W }}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold leading-snug text-slate-900">
          <span className="mr-1.5 font-mono text-mode-ink">{n}</span>
          {a} — {b}
        </p>
        <button type="button" onClick={onClose} aria-label={t('close')}
          className="rounded p-0.5 text-slate-500 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30">
          <X className="size-4" aria-hidden />
        </button>
      </div>
      {readOnly ? (
        <>
          {link.verdict && (
            <span className={cn('inline-block rounded-md px-2 py-0.5 text-xs font-medium ring-1', BADGE[link.verdict])}>
              {t(`verdict_${link.verdict}`)}
            </span>
          )}
          <p className="text-sm italic leading-relaxed text-slate-700">“{link.why}”</p>
          {link.feedback && <p className="text-sm leading-relaxed text-slate-900">{link.feedback}</p>}
        </>
      ) : (
        <>
          <textarea
            ref={box}
            rows={3}
            maxLength={400}
            value={link.why}
            onChange={(e) => onWhy(e.target.value)}
            placeholder={t('buildWhyPlaceholder')}
            className="block w-full resize-none rounded-md border border-slate-300 px-2.5 py-2 text-sm leading-relaxed text-slate-900 placeholder:text-slate-500 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
          />
          <div className="flex justify-between">
            <Button type="button" variant="ghost" size="sm" onClick={onDelete}>
              <Trash2 aria-hidden />
              {t('buildDeleteLink')}
            </Button>
            <Button type="button" size="sm" onClick={onClose}>{t('doneEditing')}</Button>
          </div>
        </>
      )}
    </div>
  )
}

function Results({ result, labelOf, onPick }: {
  result: BuildResult
  labelOf: (id: string) => string
  onPick: (id: string) => void
}) {
  const t = useTranslations('map')
  return (
    <div className="grid gap-6 border-t border-slate-200 p-4 md:grid-cols-2 md:p-5">
      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-900">{t('buildYourLinks')}</h3>
        <ol className="space-y-2">
          {result.links.map((x, i) => (
            <li key={pairId(x.from, x.to)}>
              <button
                type="button"
                onClick={() => onPick(pairId(x.from, x.to))}
                className="w-full rounded-lg px-2 py-1.5 text-left hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
              >
                <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900">
                  <span className={cn('grid size-6 place-items-center rounded-full font-mono text-xs ring-2', BADGE[x.verdict])}>{i + 1}</span>
                  {labelOf(x.from)} — {labelOf(x.to)}
                  <span className="font-normal text-slate-700">· {t(`verdict_${x.verdict}`)}</span>
                </span>
                {x.feedback && <span className="mt-1 block pl-8 text-sm leading-relaxed text-slate-800">{x.feedback}</span>}
              </button>
            </li>
          ))}
        </ol>
      </section>
      <section className="space-y-4">
        {result.missed_points.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-slate-900">{t('buildMissedPoints', { count: result.missed_points.length })}</h3>
            <ul className="space-y-1.5">
              {result.missed_points.map((p) => (
                <li key={p.label} className="text-sm leading-relaxed">
                  <span className="font-medium text-slate-900">{p.label}</span>
                  {p.point && p.point !== p.label && <span className="text-slate-700"> — {p.point}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {result.missed.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-slate-900">{t('buildMissed', { count: result.missed.length })}</h3>
            <ul className="space-y-1.5">
              {result.missed.map((m) => (
                <li key={pairId(m.from, m.to)} className="text-sm leading-relaxed">
                  <span className="font-medium text-slate-900">{labelOf(m.from)} — {labelOf(m.to)}</span>
                  {m.why && <span className="text-slate-700">: {m.why}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="text-xs leading-relaxed text-slate-600">{t('buildCounts')}</p>
      </section>
    </div>
  )
}

/** ① Recall ─ ② Link ─ ③ Compare: where the student is. */
function Steps({ current }: { current: 1 | 2 | 3 }) {
  const t = useTranslations('map')
  const names = [t('buildStep1'), t('buildStep2'), t('buildStep3')]
  return (
    <ol className="flex items-center gap-2 text-sm" aria-label={t('buildStepsLabel')}>
      {names.map((name, i) => {
        const n = i + 1
        const done = n < current
        const here = n === current
        return (
          <li key={name} className="flex min-w-0 items-center gap-2" aria-current={here ? 'step' : undefined}>
            {i > 0 && <span className={cn('h-px w-4 shrink-0 sm:w-8', done || here ? 'bg-mode' : 'bg-slate-300')} aria-hidden />}
            <span className={cn('grid size-6 shrink-0 place-items-center rounded-full font-mono text-xs font-semibold',
              here ? 'bg-mode-strong text-mode-on' : done ? 'bg-mode/15 text-mode-ink' : 'bg-slate-100 text-slate-600')}>
              {done ? <Check className="size-3.5" aria-hidden /> : n}
            </span>
            <span className={cn('truncate', here ? 'font-semibold text-slate-900' : 'text-slate-600')}>{name}</span>
          </li>
        )
      })}
    </ol>
  )
}
