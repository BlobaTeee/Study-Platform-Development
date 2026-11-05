'use client'

import '@xyflow/react/dist/style.css'
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import useSWR from 'swr'
import {
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import { ArrowRight, ChevronDown, Filter, Loader2, LocateFixed, Minus, Network, Plus, X } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { notebooksAPI, type ConceptState, type KnowledgeMapData, type MapConcept } from '@/lib/api'
import { CARD_H, CARD_W, FULL_CARD, SMALL_CARD, layoutMap } from '@/lib/map-layout'
import { formatSourceIdsForQuery } from '@/lib/source-utils'
import { cn } from '@/lib/utils'

type MapT = ReturnType<typeof useTranslations<'map'>>

// The mastery colours used across the app (lib/study-format.ts): emerald
// for strong, amber for shaky, red for weak; slate for not yet studied.
const DOT: Record<ConceptState, string> = {
  strong: 'bg-mode-analytics',
  shaky: 'bg-mode-flashcards',
  weak: 'bg-red-500',
  not_studied: 'bg-white ring-1 ring-inset ring-slate-400',
}
const BAR: Record<ConceptState, string> = {
  strong: 'bg-mode-analytics',
  shaky: 'bg-mode-flashcards',
  weak: 'bg-red-400',
  not_studied: 'bg-slate-300',
}
// The state word in the same hue, one step deeper so it reads on white.
const WORD: Record<ConceptState, string> = {
  strong: 'text-mode-analytics-ink',
  shaky: 'text-mode-flashcards-ink',
  weak: 'text-red-700',
  not_studied: 'text-slate-600',
}

/** Which signal is the weaker, as the server decides it (ties go to
 *  understanding): the one the colour and the action follow. */
function weakerSide(c: MapConcept): 'understanding' | 'memory' | null {
  if (!c.understanding && !c.memory) return null
  if (!c.memory) return 'understanding'
  if (!c.understanding) return 'memory'
  return c.memory.p < c.understanding.p ? 'memory' : 'understanding'
}

function weakerP(c: MapConcept): number | null {
  const side = weakerSide(c)
  return side ? c[side]!.p : null
}

/** "nhớ 2/2 thẻ · 4 thẻ chưa học": the count is over the cards reviewed. */
const memoryText = (c: MapConcept, t: MapT) =>
  c.memory
    ? [
        t('memoryLine', { remembered: c.memory.remembered, total: c.memory.total }),
        c.memory.unseen > 0 ? t('unseenLine', { count: c.memory.unseen }) : null,
      ]
        .filter(Boolean)
        .join(' · ')
    : null
const understandingText = (c: MapConcept, t: MapT) =>
  c.understanding ? t('understandingLine', { correct: c.understanding.correct, total: c.understanding.total }) : null

/** "nhớ 2/6 thẻ · đúng 4/5 câu", or "chưa luyện". */
function numbersLine(c: MapConcept, t: MapT): string {
  const parts = [memoryText(c, t), understandingText(c, t)].filter(Boolean)
  return parts.length ? parts.join(' · ') : t('notStudiedLine')
}

function StateDot({ state, className }: { state: ConceptState; className?: string }) {
  return <span aria-hidden className={cn('inline-block size-2.5 shrink-0 rounded-full', DOT[state], className)} />
}

/** What the cards read from the map around them; kept out of node data so a
 *  selection does not rebuild (and re-measure) every node. */
type MapView = {
  selected: string | null
  onlyWeak: boolean
  /** In a document's page: small cards, a name and a dot. */
  compact: boolean
  select: (key: string) => void
  /** Pan a card into view if it is outside the canvas. */
  reveal: (key: string) => void
}
const MapViewContext = createContext<MapView>({ selected: null, onlyWeak: false, compact: false, select: () => {}, reveal: () => {} })

type ConceptNodeType = Node<{ concept: MapConcept }, 'concept'>

function ConceptNode({ data }: NodeProps<ConceptNodeType>) {
  const t = useTranslations('map')
  const { selected, onlyWeak, compact, select, reveal } = useContext(MapViewContext)
  const c = data.concept
  const isSelected = selected === c.key
  const faded = onlyWeak && c.state === 'strong'
  const p = weakerP(c)
  const once = c.events === 1
  return (
    <>
      <Handle type="target" position={Position.Left} isConnectable={false} className="!opacity-0" />
      <button
        type="button"
        data-concept={c.key}
        onClick={() => select(c.key)}
        // Keyboard focus only: a click lands on a card already in sight.
        onFocus={(e) => {
          if (e.currentTarget.matches(':focus-visible')) reveal(c.key)
        }}
        aria-pressed={isSelected}
        aria-label={`${c.label}. ${t(`state_${c.state}`)}. ${numbersLine(c, t)}${once ? `, ${t('once')}` : ''}`}
        style={compact ? { width: SMALL_CARD.w, height: SMALL_CARD.h } : { width: CARD_W, height: CARD_H }}
        className={cn(
          'flex overflow-hidden rounded-xl border bg-white text-left shadow-sheet outline-none',
          compact ? 'items-center gap-2 px-3 py-2' : 'flex-col gap-2 px-3.5 py-3',
          'transition-[opacity,box-shadow,border-color] duration-200 motion-reduce:transition-none',
          'hover:shadow-lift focus-visible:ring-[3px] focus-visible:ring-mode/30',
          c.state === 'weak' ? 'border-red-200' : 'border-slate-200',
          once && 'border-dashed',
          isSelected && 'border-mode shadow-lift ring-[3px] ring-mode/30',
          faded && 'opacity-40',
        )}
      >
        {compact ? (
          <>
            <StateDot state={c.state} className="shrink-0" />
            <span className="line-clamp-2 text-sm font-medium leading-[18px] text-slate-900">{c.label}</span>
          </>
        ) : (
        <span className="flex items-start gap-2">
          <StateDot state={c.state} className="mt-[6px]" />
          <span className="line-clamp-2 text-base font-medium leading-[21px] text-slate-900">{c.label}</span>
        </span>
        )}
        {!compact && (<>
        {/* The state in words as well as colour, beside its bar. */}
        <span className="mt-auto flex items-center gap-2.5" aria-hidden>
          <span className={cn('shrink-0 text-[13px] font-semibold leading-[18px]', WORD[c.state])}>
            {t(`state_${c.state}`)}
          </span>
          <span className="block h-[5px] min-w-0 flex-1 overflow-hidden rounded-full bg-slate-100">
            {p !== null && (
              <span
                className={cn('block h-full rounded-full', BAR[c.state])}
                style={{ width: `${Math.max(4, Math.round(p * 100))}%` }}
              />
            )}
          </span>
        </span>
        <span className="line-clamp-2 font-mono text-[13px] leading-[17px] text-slate-600 tabular-nums">
          {numbersLine(c, t)}
          {once && <span className="text-slate-700">{` · ${t('once')}`}</span>}
        </span>
        </>)}
      </button>
      <Handle type="source" position={Position.Right} isConnectable={false} className="!opacity-0" />
    </>
  )
}

const nodeTypes = { concept: ConceptNode }

/** One links request per notebook and concept set at a time, shared across
 *  remounts: switching views while links are being found joins the request
 *  already on its way instead of sending a second. Cleared once settled. */
const linksInFlight = new Map<string, Promise<unknown>>()
function linksRequest(notebookId: number, set: string): Promise<unknown> {
  const pending = linksInFlight.get(set)
  if (pending) return pending
  const request = notebooksAPI.findMapLinks(notebookId).finally(() => linksInFlight.delete(set))
  linksInFlight.set(set, request)
  return request
}

/** The knowledge map of one notebook: each main idea is a paper card coloured
 *  by the student's weaker side (understanding or memory), arrows say "learn
 *  this first". Links are found once by the server and cached; until then
 *  the cards show without arrows. */
/** The notebook's map, or with `sourceId` only one document's concepts and the
 *  links between them, sized to sit inside that document's page. */
export function KnowledgeMap({ notebookId, sourceId }: { notebookId: number; sourceId?: number }) {
  const t = useTranslations('map')
  // Compare the payload, not the axios response (a new object every fetch):
  // a refetch that brings the same map keeps the same data, so nothing
  // downstream rebuilds.
  const { data, error, mutate } = useSWR(['/map', notebookId], () => notebooksAPI.getMap(notebookId), {
    compare: (a, b) => JSON.stringify(a?.data) === JSON.stringify(b?.data),
  })
  const whole: KnowledgeMapData | undefined = data?.data
  // One document's part of the map: its concepts, and links with both ends among them.
  const map = useMemo<KnowledgeMapData | undefined>(() => {
    if (!whole || sourceId === undefined) return whole
    const concepts = whole.concepts.filter((c) => c.source_ids.includes(sourceId))
    const keys = new Set(concepts.map((c) => c.key))
    return { ...whole, concepts, edges: whole.edges.filter((e) => keys.has(e.from) && keys.has(e.to)), missing_key_points: [] }
  }, [whole, sourceId])

  // `missing` means the concepts changed since links were last found. Ask
  // once per set of concepts (reading a new document changes the set and
  // asks again); a failure leaves the cards up with a retry line. A failure
  // belongs to its set, so a new set starts clean.
  const asked = useRef<string | null>(null)
  const conceptSet = whole ? `${notebookId}:${whole.concepts.map((c) => c.key).join('|')}` : null
  const [failedFor, setFailedFor] = useState<string | null>(null)
  const findLinks = useCallback(
    (set: string) => {
      linksRequest(notebookId, set)
        .then(() => mutate())
        .catch(() => setFailedFor(set))
    },
    [notebookId, mutate],
  )
  useEffect(() => {
    if (map?.edges_status !== 'missing' || !conceptSet || asked.current === conceptSet) return
    asked.current = conceptSet
    findLinks(conceptSet)
  }, [map?.edges_status, conceptSet, findLinks])
  const retryLinks = () => {
    if (!conceptSet) return
    setFailedFor(null)
    findLinks(conceptSet)
  }
  const linksFailed = failedFor !== null && failedFor === conceptSet && map?.edges_status === 'missing'
  const linksPending = map?.edges_status === 'missing' && !linksFailed

  if (error && !map)
    return (
      <div role="alert" className="sheet flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-4 text-base text-red-700">
        {t('failed')}
        <Button type="button" variant="outline" size="sm" onClick={() => void mutate()}>
          {t('retry')}
        </Button>
      </div>
    )
  if (!map) return <div className="sheet h-[70dvh] min-h-[420px] animate-pulse motion-reduce:animate-none" aria-busy />
  if (map.concepts.length === 0) return <EmptyMap missing={map.missing_key_points} onRead={() => mutate()} />
  const inDocument = sourceId !== undefined
  return (
    <div className="space-y-3">
      {!inDocument && <p className="max-w-prose text-sm leading-relaxed text-slate-600">{t('lead')}</p>}
      {map.missing_key_points.length > 0 && (
        <MissingNote missing={map.missing_key_points} onRead={() => mutate()} />
      )}
      <ReactFlowProvider>
        <MapCanvas
          notebookId={notebookId}
          map={map}
          compact={inDocument}
          linksPending={linksPending}
          linksFailed={linksFailed}
          onRetryLinks={retryLinks}
        />
      </ReactFlowProvider>
    </div>
  )
}

type Missing = KnowledgeMapData['missing_key_points']

/** "Rút ý chính" for one document: reads its main ideas, then the map
 *  refetches with the new concepts. */
function ReadButton({ sourceId, onRead }: { sourceId: number; onRead: () => void }) {
  const t = useTranslations('map')
  const [reading, setReading] = useState(false)
  const [failed, setFailed] = useState(false)
  const read = async () => {
    setReading(true)
    setFailed(false)
    try {
      await notebooksAPI.readSource(sourceId)
      onRead()
    } catch {
      setFailed(true)
    } finally {
      setReading(false)
    }
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button type="button" variant="tinted" size="sm" disabled={reading} onClick={() => void read()}>
        {reading && <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden />}
        {t('readKeyPoints')}
      </Button>
      {failed && (
        <span role="alert" className="text-sm text-red-700">
          {t('failed')}
        </span>
      )}
    </span>
  )
}

function EmptyMap({ missing, onRead }: { missing: Missing; onRead: () => void }) {
  const t = useTranslations('map')
  return (
    <div className="sheet paper-grid px-5 py-12 md:py-16">
      <div className="mx-auto max-w-md space-y-5 text-center">
        <Network className="mx-auto size-8 text-mode" aria-hidden />
        <p className="text-base leading-relaxed text-slate-700">{t('noConcepts')}</p>
        {missing.length > 0 && (
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white text-left">
            {missing.map((m) => (
              <li key={m.source_id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
                <span className="min-w-0 flex-1 truncate text-sm text-slate-900">{m.title}</span>
                <ReadButton sourceId={m.source_id} onRead={onRead} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/** Some documents have no main ideas yet, so the map leaves them out. */
function MissingNote({ missing, onRead }: { missing: Missing; onRead: () => void }) {
  const t = useTranslations('map')
  return (
    <details className="group text-sm text-slate-600">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 hover:text-slate-900 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 truncate">{t('missingKeyPoints', { titles: missing.map((m) => m.title).join(', ') })}</span>
        <ChevronDown
          className="size-4 shrink-0 transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none"
          aria-hidden
        />
      </summary>
      <ul className="mt-2 space-y-2">
        {missing.map((m) => (
          <li key={m.source_id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-slate-900">{m.title}</span>
            <ReadButton sourceId={m.source_id} onRead={onRead} />
          </li>
        ))}
      </ul>
    </details>
  )
}

const motionMs = (ms: number) =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : ms

const FIT_GUTTER = 24
// Never fit so small that a card stops being readable (label 16px and
// numbers 13px stay at least 13.6px and 11px on screen): a map wider than
// the canvas starts at its left edge (where the prerequisites are) and is
// panned, rather than shrunk to a postage stamp.
const FIT_FLOOR = 0.85
// In a document's page: small enough to fit its width, never too small to read.
const COMPACT_FLOOR = 0.75
const COMPACT_MAX_H = 960

/** Where to place the map in a canvas of w × h. Computed from the layout's
 *  own positions, so it needs no measured nodes and is the same every time. */
function fitViewport(points: { x: number; y: number }[], w: number, h: number, floor = FIT_FLOOR, card = FULL_CARD) {
  if (!points.length || !w || !h) return null
  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const minX = Math.min(...xs)
  const minY = Math.min(...ys)
  const bw = Math.max(...xs) + card.w - minX
  const bh = Math.max(...ys) + card.h - minY
  const fit = Math.min((w - 2 * FIT_GUTTER) / bw, (h - 2 * FIT_GUTTER) / bh)
  const zoom = Math.min(1, Math.max(floor, fit))
  const x = bw * zoom <= w - 2 * FIT_GUTTER ? (w - bw * zoom) / 2 - minX * zoom : FIT_GUTTER - minX * zoom
  const y = bh * zoom <= h - 2 * FIT_GUTTER ? (h - bh * zoom) / 2 - minY * zoom : FIT_GUTTER - minY * zoom
  return { x, y, zoom }
}

const EDGE = 'var(--color-slate-400)'
const EDGE_ACTIVE = 'var(--color-mode-library)'

function MapCanvas({
  notebookId,
  map,
  compact = false,
  linksPending,
  linksFailed,
  onRetryLinks,
}: {
  notebookId: number
  map: KnowledgeMapData
  /** Inside a document's page: the detail panel goes under the canvas, not beside it. */
  compact?: boolean
  linksPending: boolean
  linksFailed: boolean
  onRetryLinks: () => void
}) {
  const t = useTranslations('map')
  const { setViewport, setCenter, getViewport, zoomIn, zoomOut } = useReactFlow()
  const canvasRef = useRef<HTMLDivElement>(null)
  const [placed, setPlaced] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [onlyWeak, setOnlyWeak] = useState(false)

  // One card per key, in the order the server sends them, so the layout
  // (deterministic for a given order) is the same picture every visit.
  const concepts = useMemo(() => {
    const seen = new Set<string>()
    return map.concepts.filter((c) => !seen.has(c.key) && seen.add(c.key))
  }, [map.concepts])
  const byKey = useMemo(() => new Map(concepts.map((c) => [c.key, c])), [concepts])
  const links = useMemo(() => {
    const seen = new Set<string>()
    return map.edges.filter((e) => {
      const id = `${e.from}->${e.to}`
      if (seen.has(id) || !byKey.has(e.from) || !byKey.has(e.to) || e.from === e.to) return false
      seen.add(id)
      return true
    })
  }, [map.edges, byKey])

  // The layout depends only on which cards exist and how they link. Held as
  // plain strings, a refetch that only moves mastery numbers leaves the
  // positions, and so the viewport the student panned to, alone.
  const keySig = JSON.stringify(concepts.map((c) => c.key))
  const linkSig = JSON.stringify(links.map((e) => [e.from, e.to]))
  const card = compact ? SMALL_CARD : FULL_CARD
  const positions = useMemo(
    () =>
      layoutMap(
        JSON.parse(keySig) as string[],
        (JSON.parse(linkSig) as [string, string][]).map(([from, to]) => ({ from, to })),
        compact ? SMALL_CARD : FULL_CARD,
      ),
    [keySig, linkSig, compact],
  )

  // Built from the data alone: selection and fading reach the cards through
  // context, so clicking a card does not hand React Flow new nodes to measure.
  const nodes = useMemo<ConceptNodeType[]>(
    () =>
      concepts.map((c) => ({
        id: c.key,
        type: 'concept',
        position: positions[c.key],
        data: { concept: c },
        draggable: false,
        selectable: true,
      })),
    [concepts, positions],
  )

  const edges = useMemo<Edge[]>(
    () =>
      links.map((e) => {
        const active = selected === e.to
        const faded = onlyWeak && byKey.get(e.from)?.state === 'strong' && byKey.get(e.to)?.state === 'strong'
        const color = active ? EDGE_ACTIVE : EDGE
        return {
          id: `${e.from}->${e.to}`,
          source: e.from,
          target: e.to,
          type: 'default',
          animated: false,
          focusable: false,
          selectable: false,
          zIndex: active ? 1 : 0,
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
          style: { stroke: color, strokeWidth: active ? 2.25 : 1.5, opacity: faded ? 0.3 : 1 },
        }
      }),
    [links, selected, onlyWeak, byKey],
  )

  // Fit on open (the canvas fades in once placed), and again only when the
  // layout itself changes, such as arrows arriving and moving cards into layers.
  // Inside a document's page the canvas is as tall as the document's map
  // needs at the zoom that fits its width, so nothing is cut off at the side.
  const [canvasW, setCanvasW] = useState(0)
  useLayoutEffect(() => {
    const el = canvasRef.current
    if (!compact || !el) return
    const watch = new ResizeObserver(() => setCanvasW(el.clientWidth))
    watch.observe(el)
    return () => watch.disconnect()
  }, [compact])
  const compactHeight = useMemo(() => {
    const pts = Object.values(positions)
    if (!compact || !pts.length || !canvasW) return undefined
    const bw = Math.max(...pts.map((p) => p.x)) + SMALL_CARD.w - Math.min(...pts.map((p) => p.x))
    const bh = Math.max(...pts.map((p) => p.y)) + SMALL_CARD.h - Math.min(...pts.map((p) => p.y))
    const zoom = Math.min(1, Math.max(COMPACT_FLOOR, (canvasW - 2 * FIT_GUTTER) / bw))
    return Math.round(Math.min(COMPACT_MAX_H, Math.max(320, bh * zoom + 2 * FIT_GUTTER)))
  }, [compact, positions, canvasW])

  const fit = useCallback(
    (duration: number) => {
      const el = canvasRef.current
      const vp = el && fitViewport(Object.values(positions), el.clientWidth, el.clientHeight, compact ? COMPACT_FLOOR : FIT_FLOOR, card)
      if (!vp) return Promise.resolve(false)
      return setViewport(vp, { duration })
    },
    // compactHeight: a taller canvas is fitted again once it has grown.
    [positions, setViewport, compact, compactHeight, card], // eslint-disable-line react-hooks/exhaustive-deps
  )

  const placedOnce = useRef(false)
  useEffect(() => {
    const first = !placedOnce.current
    placedOnce.current = true
    void fit(first ? 0 : motionMs(300)).then(() => setPlaced(true))
  }, [fit])

  // Centre a card; with `onlyIfHidden`, only when it is not wholly inside
  // the canvas (keyboard focus must never land on a card out of sight).
  const centerOn = useCallback(
    (key: string, onlyIfHidden: boolean) => {
      const p = positions[key]
      const el = canvasRef.current
      if (!p || !el) return
      const { x, y, zoom } = getViewport()
      if (onlyIfHidden) {
        const left = p.x * zoom + x
        const top = p.y * zoom + y
        const inside = left >= 0 && top >= 0 && left + card.w * zoom <= el.clientWidth && top + card.h * zoom <= el.clientHeight
        if (inside) return
      }
      void setCenter(p.x + card.w / 2, p.y + card.h / 2, {
        zoom: onlyIfHidden ? zoom : Math.max(zoom, FIT_FLOOR),
        duration: motionMs(350),
      })
    },
    [positions, getViewport, setCenter, card],
  )

  // After selecting from the panel or the list, focus moves to the new
  // panel's heading (the old panel, and the button pressed, are gone).
  const focusHeadingRef = useRef(false)
  const select = useCallback((key: string) => {
    focusHeadingRef.current = false
    setSelected((k) => (k === key ? null : key))
  }, [])
  const reveal = useCallback((key: string) => centerOn(key, true), [centerOn])
  const view = useMemo(() => ({ selected, onlyWeak, compact, select, reveal }), [selected, onlyWeak, compact, select, reveal])
  const current = selected ? byKey.get(selected) ?? null : null

  // From the panel or the list: select the card and bring it into view.
  const focusConcept = useCallback(
    (key: string) => {
      focusHeadingRef.current = key !== selected
      setSelected(key)
      centerOn(key, false)
    },
    [selected, centerOn],
  )

  // Escape closes the panel and hands focus back to the card it was about.
  const close = useCallback(() => {
    const key = selected
    setSelected(null)
    if (key) document.querySelector<HTMLElement>(`[data-concept="${CSS.escape(key)}"]`)?.focus({ preventScroll: true })
  }, [selected])
  useEffect(() => {
    if (!selected) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      // Escape inside a field or another dialog belongs to that, not the map.
      const target = e.target instanceof Element ? e.target : null
      if (target?.closest('input, textarea, select, [contenteditable="true"], [role="dialog"]')) return
      close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected, close])

  return (
    <MapViewContext.Provider value={view}>
      <div className={cn('sheet overflow-hidden', !compact && 'md:grid md:grid-cols-[minmax(0,1fr)_20rem]')}>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-slate-200 px-3 py-2 md:px-4">
            <ul className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600">
              {(['strong', 'shaky', 'weak', 'not_studied'] as const).map((s) => (
                <li key={s} className="inline-flex items-center gap-1.5">
                  <StateDot state={s} />
                  {t(`state_${s}`)}
                </li>
              ))}
            </ul>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t('zoomOut')}
                title={t('zoomOut')}
                onClick={() => void zoomOut({ duration: motionMs(200) })}
              >
                <Minus aria-hidden />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t('zoomIn')}
                title={t('zoomIn')}
                onClick={() => void zoomIn({ duration: motionMs(200) })}
              >
                <Plus aria-hidden />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => void fit(motionMs(300))}
              >
                <LocateFixed aria-hidden />
                {t('recenter')}
              </Button>
              <Button
                type="button"
                variant={onlyWeak ? 'tinted' : 'ghost'}
                size="sm"
                aria-pressed={onlyWeak}
                onClick={() => setOnlyWeak((v) => !v)}
              >
                <Filter aria-hidden />
                {t('onlyWeak')}
              </Button>
            </div>
          </div>
          {/* Above the canvas, so it never covers a card. Always mounted so
              the change is announced. */}
          <div
            role="status"
            className={cn(
              (linksPending || linksFailed) &&
                'flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 md:px-4',
            )}
          >
            {linksPending ? (
              <>
                <Loader2 className="size-4 animate-spin text-mode motion-reduce:animate-none" aria-hidden />
                {t('linksPending')}
              </>
            ) : linksFailed ? (
              <>
                {t('linksFailed')}
                <Button type="button" variant="link" size="sm" className="h-auto px-0" onClick={onRetryLinks}>
                  {t('retry')}
                </Button>
              </>
            ) : null}
          </div>
          <div
            ref={canvasRef}
            style={compact ? { height: compactHeight ?? 420 } : undefined}
            className={cn(
              'relative bg-white',
              compact ? 'min-h-[320px]' : 'h-[70dvh] min-h-[420px]',
              '[&_.react-flow__viewport]:transition-opacity [&_.react-flow__viewport]:duration-300 motion-reduce:[&_.react-flow__viewport]:transition-none',
              !placed && '[&_.react-flow__viewport]:opacity-0',
              '[&_.react-flow__edge-path]:transition-[stroke,stroke-width,opacity] [&_.react-flow__edge-path]:duration-200',
              'motion-reduce:[&_.react-flow__edge-path]:transition-none',
            )}
          >
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              minZoom={0.3}
              maxZoom={1.6}
              nodesConnectable={false}
              nodesDraggable={false}
              nodesFocusable={false}
              edgesFocusable={false}
              zoomOnScroll={false}
              preventScrolling={false}
              onPaneClick={() => setSelected(null)}
              proOptions={{ hideAttribution: true }}
            >
              <Background variant={BackgroundVariant.Lines} gap={22} color="var(--color-slate-100)" />
            </ReactFlow>
          </div>
        </div>
        {/* Desktop: a column beside the canvas, always there so selecting a
            card never resizes the canvas under the pointer. Absolute inner so
            a long panel scrolls instead of stretching the map. */}
        <aside className="relative hidden border-l border-slate-200 md:block">
          <div className="absolute inset-0 overflow-y-auto">
            {current ? (
              <ConceptDetail
                key={current.key}
                concept={current}
                byKey={byKey}
                links={links}
                notebookId={notebookId}
                onSelect={focusConcept}
                focusRequestRef={focusHeadingRef}
              />
            ) : (
              <p className="p-5 text-sm text-slate-600">{t('pickHint')}</p>
            )}
          </div>
        </aside>
      </div>
      {/* The same map for a screen reader, in reading order. Its buttons
          stay out of the Tab order: the cards themselves are the tab stops. */}
      <ul aria-label={t('listLabel')} className="sr-only">
        {concepts.map((c) => (
          <li key={c.key}>
            <button type="button" tabIndex={-1} aria-pressed={selected === c.key} onClick={() => focusConcept(c.key)}>
              {`${c.label}. ${t(`state_${c.state}`)}. ${numbersLine(c, t)}`}
            </button>
          </li>
        ))}
      </ul>
      {/* Phone: a bottom sheet over the canvas. */}
      {current && (
        <div
          role="region"
          aria-label={current.label}
          className={cn(
            'fixed inset-x-0 bottom-0 z-40 max-h-[60dvh] overflow-y-auto rounded-t-2xl border-t border-slate-200 bg-white shadow-lift md:hidden',
            'animate-in fade-in slide-in-from-bottom-6 duration-200 motion-reduce:animate-none',
          )}
        >
          <div className="sticky top-0 flex justify-end bg-white/95 px-2 pt-2">
            <span aria-hidden className="absolute left-1/2 top-2 h-1 w-10 -translate-x-1/2 rounded-full bg-slate-200" />
            <Button type="button" variant="ghost" size="icon-sm" onClick={close} aria-label={t('close')}>
              <X aria-hidden />
            </Button>
          </div>
          <ConceptDetail
            key={current.key}
            concept={current}
            byKey={byKey}
            links={links}
            notebookId={notebookId}
            onSelect={focusConcept}
            focusRequestRef={focusHeadingRef}
            className="pt-0"
          />
        </div>
      )}
    </MapViewContext.Provider>
  )
}

/** Everything about one concept: its two signals with the weaker marked,
 *  what to do about it, and what to understand first and why. */
function ConceptDetail({
  concept: c,
  byKey,
  links,
  notebookId,
  onSelect,
  focusRequestRef,
  className,
}: {
  concept: MapConcept
  byKey: Map<string, MapConcept>
  links: KnowledgeMapData['edges']
  notebookId: number
  onSelect: (key: string) => void
  /** Set when this panel replaces another by a press inside the panel or the
   *  list: the visible copy (desktop column or phone sheet) takes focus. */
  focusRequestRef: React.RefObject<boolean>
  className?: string
}) {
  const t = useTranslations('map')
  const router = useRouter()
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    const h = headingRef.current
    if (!focusRequestRef.current || !h || h.offsetParent === null) return
    focusRequestRef.current = false
    h.focus({ preventScroll: true })
  }, [focusRequestRef])
  const [practising, setPractising] = useState(false)
  const [error, setError] = useState('')
  const side = weakerSide(c)
  const first = c.first ? byKey.get(c.first) : undefined
  const needs = links.filter((e) => e.to === c.key)

  // Advice that claims something about the other side only when that side
  // has been measured; a single signal speaks through its numbers alone.
  const advice =
    c.state === 'strong' ? t('adviceStrong')
    : c.state === 'not_studied' ? t('adviceStart')
    : side === 'memory' && c.understanding ? t('adviceMemory')
    : side === 'understanding' && c.memory ? t('adviceUnderstanding')
    : null

  const practise = async () => {
    setPractising(true)
    setError('')
    try {
      const res = await notebooksAPI.practiseConcept(notebookId, c.key)
      router.push(`/dashboard/quizzes?source=${formatSourceIdsForQuery(res.data.source_ids)}&quiz=${res.data.quiz_id}`)
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail || t('failed'))
      setPractising(false)
    }
  }

  const signal = (which: 'understanding' | 'memory') => {
    const text = which === 'understanding' ? understandingText(c, t) : memoryText(c, t)
    const p = c[which]?.p ?? null
    const weaker = side === which && c.state !== 'strong'
    return (
      <li key={which} className="space-y-1.5">
        <p className="flex items-baseline justify-between gap-3 text-sm">
          <span className={cn(weaker ? 'font-medium text-slate-900' : 'text-slate-600')}>{t(which)}</span>
          <span className={cn('font-mono text-xs tabular-nums', weaker ? 'font-medium text-slate-900' : 'text-slate-600')}>
            {text ?? t('notStudiedLine')}
          </span>
        </p>
        <div className="h-[5px] overflow-hidden rounded-full bg-slate-100" aria-hidden>
          {p !== null && (
            <div
              className={cn('h-full rounded-full', weaker ? BAR[c.state] : 'bg-slate-300')}
              style={{ width: `${Math.max(4, Math.round(p * 100))}%` }}
            />
          )}
        </div>
      </li>
    )
  }

  const action = c.action
  return (
    <div className={cn('space-y-5 p-5', className)}>
      <div className="space-y-1.5">
        <h3
          ref={headingRef}
          tabIndex={-1}
          className="font-display text-lg font-semibold leading-snug text-slate-900 outline-none"
        >
          {c.label}
        </h3>
        <p className="flex items-center gap-2 text-sm text-slate-700">
          <StateDot state={c.state} />
          {t(`state_${c.state}`)}
          {c.events === 1 && <span className="text-slate-600">· {t('once')}</span>}
        </p>
        {c.point && c.point !== c.label && <p className="text-sm leading-relaxed text-slate-600">{c.point}</p>}
      </div>

      <ul className="space-y-3">
        {signal('understanding')}
        {signal('memory')}
      </ul>

      {advice && <p className="text-sm leading-relaxed text-slate-700">{advice}</p>}

      {first && (
        <div className="space-y-1.5 border-t border-slate-100 pt-4">
          <p className="text-sm leading-relaxed text-slate-700">
            {t('firstNeeds', { label: first.label, state: t(`state_${first.state}`).toLowerCase() })}
          </p>
          <Button type="button" variant="link" size="sm" className="h-auto px-0" onClick={() => onSelect(first.key)}>
            {t('goFirst', { label: first.label })}
            <ArrowRight aria-hidden />
          </Button>
        </div>
      )}

      {action && (
        <div data-mode={action.kind === 'cards' ? 'flashcards' : 'quizzes'} className="space-y-2">
          {action.kind === 'cards' ? (
            <Button asChild className="w-full">
              <Link href={`/dashboard/flashcards?cards=${action.card_ids.join(',')}`}>
                {t('actionCards', { count: action.card_ids.length })}
              </Link>
            </Button>
          ) : action.kind === 'exercise' ? (
            <Button asChild className="w-full">
              <Link href={`/dashboard/practice/${action.exercise_id}`}>{t('actionExercise')}</Link>
            </Button>
          ) : (
            <Button type="button" className="w-full" disabled={practising} onClick={() => void practise()}>
              {practising && <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden />}
              {practising ? t('practising') : t('actionPractice')}
            </Button>
          )}
          {error && (
            <p role="alert" className="text-sm text-red-700">
              {error}
            </p>
          )}
        </div>
      )}

      {needs.length > 0 && (
        <div className="space-y-3 border-t border-slate-100 pt-4">
          <h4 className="text-sm font-semibold text-slate-900">{t('needs')}</h4>
          <ul className="space-y-3">
            {needs.map((e) => {
              const from = byKey.get(e.from)
              if (!from) return null
              return (
                <li key={e.from} className="space-y-0.5">
                  <button
                    type="button"
                    onClick={() => onSelect(from.key)}
                    className="inline-flex items-center gap-2 rounded text-left text-sm font-medium text-slate-900 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                  >
                    <StateDot state={from.state} />
                    {from.label}
                  </button>
                  {e.why && (
                    <p className="pl-[18px] text-sm leading-relaxed text-slate-600">
                      <span className="text-slate-700">{t('reason')}: </span>
                      {e.why}
                    </p>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
