'use client'

import '@xyflow/react/dist/style.css'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
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
import { CARD_H, CARD_W, layoutMap } from '@/lib/map-layout'
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

const memoryText = (c: MapConcept, t: MapT) =>
  c.memory ? t('memoryLine', { remembered: c.memory.remembered, total: c.memory.total }) : null
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
type MapView = { selected: string | null; onlyWeak: boolean; select: (key: string) => void }
const MapViewContext = createContext<MapView>({ selected: null, onlyWeak: false, select: () => {} })

type ConceptNodeType = Node<{ concept: MapConcept }, 'concept'>

function ConceptNode({ data }: NodeProps<ConceptNodeType>) {
  const t = useTranslations('map')
  const { selected, onlyWeak, select } = useContext(MapViewContext)
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
        aria-pressed={isSelected}
        aria-label={`${c.label}. ${t(`state_${c.state}`)}. ${numbersLine(c, t)}${once ? `, ${t('once')}` : ''}`}
        style={{ width: CARD_W, minHeight: CARD_H }}
        className={cn(
          'flex flex-col gap-2 rounded-xl border bg-white px-3 py-2.5 text-left shadow-sheet outline-none',
          'transition-[opacity,box-shadow,border-color] duration-200 motion-reduce:transition-none',
          'hover:shadow-lift focus-visible:ring-[3px] focus-visible:ring-mode/30',
          c.state === 'weak' ? 'border-red-200' : 'border-slate-200',
          once && 'border-dashed',
          isSelected && 'border-mode shadow-lift ring-[3px] ring-mode/30',
          faded && 'opacity-40',
        )}
      >
        <span className="flex items-start gap-2">
          <StateDot state={c.state} className="mt-1.5" />
          <span className="line-clamp-2 text-[15px] font-medium leading-5 text-slate-900">{c.label}</span>
        </span>
        <span className="mt-auto block h-[5px] overflow-hidden rounded-full bg-slate-100" aria-hidden>
          {p !== null && (
            <span
              className={cn('block h-full rounded-full', BAR[c.state])}
              style={{ width: `${Math.max(4, Math.round(p * 100))}%` }}
            />
          )}
        </span>
        <span className="line-clamp-2 font-mono text-[11px] leading-4 text-slate-600 tabular-nums">
          {numbersLine(c, t)}
          {once && <span className="text-slate-700">{` · ${t('once')}`}</span>}
        </span>
      </button>
      <Handle type="source" position={Position.Right} isConnectable={false} className="!opacity-0" />
    </>
  )
}

const nodeTypes = { concept: ConceptNode }

/** The knowledge map of one notebook: each main idea is a paper card coloured
 *  by the student's weaker side (understanding or memory), arrows say "learn
 *  this first". Links are found once by the server and cached; until then
 *  the cards show without arrows. */
export function KnowledgeMap({ notebookId }: { notebookId: number }) {
  const t = useTranslations('map')
  const { data, error, mutate } = useSWR(['/map', notebookId], () => notebooksAPI.getMap(notebookId))
  const map: KnowledgeMapData | undefined = data?.data

  // `missing` means the concepts changed since links were last found. Ask
  // once per set of concepts (reading a new document changes the set and
  // asks again); a failure leaves the cards up with a retry line.
  const asked = useRef<string | null>(null)
  const conceptSet = map ? `${notebookId}:${map.concepts.map((c) => c.key).join('|')}` : null
  const [linksFailed, setLinksFailed] = useState(false)
  const findLinks = useCallback(() => {
    notebooksAPI
      .findMapLinks(notebookId)
      .then(() => mutate())
      .catch(() => setLinksFailed(true))
  }, [notebookId, mutate])
  useEffect(() => {
    if (map?.edges_status !== 'missing' || asked.current === conceptSet) return
    asked.current = conceptSet
    findLinks()
  }, [map?.edges_status, conceptSet, findLinks])
  const retryLinks = () => {
    setLinksFailed(false)
    findLinks()
  }
  const linksPending = map?.edges_status === 'missing' && !linksFailed

  if (error) return <p role="alert" className="text-base text-red-700">{t('failed')}</p>
  if (!map) return <div className="sheet h-[70dvh] min-h-[420px] animate-pulse motion-reduce:animate-none" aria-busy />
  if (map.concepts.length === 0) return <EmptyMap missing={map.missing_key_points} onRead={() => mutate()} />
  return (
    <div className="space-y-3">
      <p className="max-w-prose text-sm leading-relaxed text-slate-600">{t('lead')}</p>
      {map.missing_key_points.length > 0 && (
        <MissingNote missing={map.missing_key_points} onRead={() => mutate()} />
      )}
      <ReactFlowProvider>
        <MapCanvas
          notebookId={notebookId}
          map={map}
          linksPending={linksPending}
          linksFailed={linksFailed && map.edges_status === 'missing'}
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
// Never fit so small that the labels stop being readable: a map wider than
// the canvas starts at its left edge (where the prerequisites are) and is
// panned, rather than shrunk to a postage stamp. A phone gets the higher
// floor: its canvas is narrow and pinching is at hand.
const fitFloor = (w: number) => (w < 640 ? 0.75 : 0.65)

/** Where to place the map in a canvas of w × h. Computed from the layout's
 *  own positions, so it needs no measured nodes and is the same every time. */
function fitViewport(nodes: { position: { x: number; y: number } }[], w: number, h: number) {
  if (!nodes.length || !w || !h) return null
  const xs = nodes.map((n) => n.position.x)
  const ys = nodes.map((n) => n.position.y)
  const minX = Math.min(...xs)
  const minY = Math.min(...ys)
  const bw = Math.max(...xs) + CARD_W - minX
  const bh = Math.max(...ys) + CARD_H - minY
  const fit = Math.min((w - 2 * FIT_GUTTER) / bw, (h - 2 * FIT_GUTTER) / bh)
  const zoom = Math.min(1, Math.max(fitFloor(w), fit))
  const x = bw * zoom <= w - 2 * FIT_GUTTER ? (w - bw * zoom) / 2 - minX * zoom : FIT_GUTTER - minX * zoom
  const y = bh * zoom <= h - 2 * FIT_GUTTER ? (h - bh * zoom) / 2 - minY * zoom : FIT_GUTTER - minY * zoom
  return { x, y, zoom }
}

const EDGE = '#94a3b8'
const EDGE_ACTIVE = '#2563eb'

function MapCanvas({
  notebookId,
  map,
  linksPending,
  linksFailed,
  onRetryLinks,
}: {
  notebookId: number
  map: KnowledgeMapData
  linksPending: boolean
  linksFailed: boolean
  onRetryLinks: () => void
}) {
  const t = useTranslations('map')
  const { setViewport, setCenter, getZoom, zoomIn, zoomOut } = useReactFlow()
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

  // Built from the data alone: selection and fading reach the cards through
  // context, so clicking a card does not hand React Flow new nodes to measure.
  const nodes = useMemo<ConceptNodeType[]>(() => {
    const pos = layoutMap(concepts.map((c) => c.key), links)
    return concepts.map((c) => ({
      id: c.key,
      type: 'concept',
      position: pos[c.key],
      data: { concept: c },
      draggable: false,
      selectable: true,
    }))
  }, [concepts, links])

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

  // Fit on open (the canvas fades in once placed), and again when arrows
  // arriving move cards into layers.
  const fit = useCallback(
    (duration: number) => {
      const el = canvasRef.current
      const vp = el && fitViewport(nodes, el.clientWidth, el.clientHeight)
      if (!vp) return Promise.resolve(false)
      return setViewport(vp, { duration })
    },
    [nodes, setViewport],
  )
  const placedOnce = useRef(false)
  useEffect(() => {
    const first = !placedOnce.current
    placedOnce.current = true
    void fit(first ? 0 : motionMs(300)).then(() => setPlaced(true))
  }, [fit])

  const select = useCallback((key: string) => setSelected((k) => (k === key ? null : key)), [])
  const view = useMemo(() => ({ selected, onlyWeak, select }), [selected, onlyWeak, select])
  const current = selected ? byKey.get(selected) ?? null : null

  // From the panel or the list: select the card and bring it into view.
  const focusConcept = useCallback(
    (key: string) => {
      setSelected(key)
      const n = nodes.find((x) => x.id === key)
      if (n) {
        void setCenter(n.position.x + CARD_W / 2, n.position.y + CARD_H / 2, {
          zoom: Math.max(getZoom(), 0.8),
          duration: motionMs(350),
        })
      }
    },
    [nodes, setCenter, getZoom],
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
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected, close])

  return (
    <MapViewContext.Provider value={view}>
      <div className="sheet overflow-hidden md:grid md:grid-cols-[minmax(0,1fr)_20rem]">
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
                {onlyWeak ? t('showAll') : t('onlyWeak')}
              </Button>
            </div>
          </div>
          <div
            ref={canvasRef}
            className={cn(
              'relative h-[70dvh] min-h-[420px] bg-white',
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
              <Background variant={BackgroundVariant.Lines} gap={22} color="#eef2f7" />
            </ReactFlow>
            {(linksPending || linksFailed) && (
              <div
                role="status"
                className="absolute left-3 right-3 top-3 z-10 flex w-fit max-w-[calc(100%-1.5rem)] flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-sm text-slate-700 shadow-sheet"
              >
                {linksPending ? (
                  <>
                    <Loader2 className="size-4 animate-spin text-mode motion-reduce:animate-none" aria-hidden />
                    {t('linksPending')}
                  </>
                ) : (
                  <>
                    {t('linksFailed')}
                    <Button type="button" variant="link" size="sm" className="h-auto px-0" onClick={onRetryLinks}>
                      {t('retry')}
                    </Button>
                  </>
                )}
              </div>
            )}
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
  className,
}: {
  concept: MapConcept
  byKey: Map<string, MapConcept>
  links: KnowledgeMapData['edges']
  notebookId: number
  onSelect: (key: string) => void
  className?: string
}) {
  const t = useTranslations('map')
  const router = useRouter()
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
      router.push(`/dashboard/quizzes?source=${res.data.source_ids.join(',')}&quiz=${res.data.quiz_id}`)
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
      <div key={which} className="space-y-1.5">
        <div className="flex items-baseline justify-between gap-3 text-sm">
          <dt className={cn(weaker ? 'font-medium text-slate-900' : 'text-slate-600')}>{t(which)}</dt>
          <dd className={cn('font-mono text-xs tabular-nums', weaker ? 'font-medium text-slate-900' : 'text-slate-600')}>
            {text ?? t('notStudiedLine')}
          </dd>
        </div>
        <div className="h-[5px] overflow-hidden rounded-full bg-slate-100" aria-hidden>
          {p !== null && (
            <div
              className={cn('h-full rounded-full', weaker ? BAR[c.state] : 'bg-slate-300')}
              style={{ width: `${Math.max(4, Math.round(p * 100))}%` }}
            />
          )}
        </div>
      </div>
    )
  }

  const action = c.action
  return (
    <div className={cn('space-y-5 p-5', className)}>
      <div className="space-y-1.5">
        <h3 className="font-display text-lg font-semibold leading-snug text-slate-900">{c.label}</h3>
        <p className="flex items-center gap-2 text-sm text-slate-700">
          <StateDot state={c.state} />
          {t(`state_${c.state}`)}
          {c.events === 1 && <span className="text-slate-600">· {t('once')}</span>}
        </p>
        {c.point && c.point !== c.label && <p className="text-sm leading-relaxed text-slate-600">{c.point}</p>}
      </div>

      <dl className="space-y-3">
        {signal('understanding')}
        {signal('memory')}
      </dl>

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
