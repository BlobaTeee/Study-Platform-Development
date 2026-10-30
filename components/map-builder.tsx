'use client'

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { ArrowLeft, Check, Loader2, RotateCcw, Trash2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { notebooksAPI } from '@/lib/api'
import {
  addLink, pairId, readyToSend, removeLink, tally,
  type BuildLink, type GradedLink, type MissedLink, type Verdict,
} from '@/lib/map-build'
import { cn } from '@/lib/utils'

type Concept = { key: string; label: string; point: string }
type Round = { id: number; concepts: Concept[] }
type Result = { links: GradedLink[]; missed: MissedLink[] }

// The verdict colours follow the map's mastery colours: emerald right,
// amber partly, red wrong; slate for what the model left out.
const LINE: Record<Verdict, string> = {
  correct: 'stroke-emerald-600',
  partial: 'stroke-amber-500',
  wrong: 'stroke-red-500',
  unjudged: 'stroke-slate-400',
}
const BADGE: Record<Verdict, string> = {
  correct: 'bg-emerald-50 text-emerald-900',
  partial: 'bg-amber-50 text-amber-900',
  wrong: 'bg-red-50 text-red-800',
  unjudged: 'bg-slate-100 text-slate-700',
}

/** Build part of the notebook's map by hand. About six concepts with no
 *  lines between them: press one, then another, to link them, and say why.
 *  Sent together, the links are graded in one request and drawn in colour,
 *  with the document's links that were missed shown dashed. */
export function MapBuilder({ notebookId, onClose }: { notebookId: number; onClose: () => void }) {
  const t = useTranslations('map')
  const [round, setRound] = useState<Round | null>(null)
  const [links, setLinks] = useState<BuildLink[]>([])
  const [picked, setPicked] = useState<string | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState<'start' | 'send' | null>('start')
  const [error, setError] = useState<string | null>(null)
  const focusWhy = useRef<string | null>(null)

  // The error is kept as a message from the server, or '' for the generic one.
  const failWith = (e: unknown) => {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    setError(typeof detail === 'string' ? detail : '')
  }

  // The first round, fetched once when the builder opens.
  useEffect(() => {
    let cancelled = false
    notebooksAPI
      .mapBuildStart(notebookId)
      .then((res) => {
        if (!cancelled) setRound(res.data)
      })
      .catch((e) => {
        if (!cancelled) failWith(e)
      })
      .finally(() => {
        if (!cancelled) setBusy(null)
      })
    return () => {
      cancelled = true
    }
  }, [notebookId])

  // Another round (or a retry): clear this one, then fetch a new one.
  const start = () => {
    setBusy('start')
    setError(null)
    setResult(null)
    setLinks([])
    setPicked(null)
    notebooksAPI
      .mapBuildStart(notebookId)
      .then((res) => setRound(res.data))
      .catch(failWith)
      .finally(() => setBusy(null))
  }

  const press = (key: string) => {
    if (result) return
    if (!picked) return setPicked(key)
    if (picked === key) return setPicked(null)
    const next = addLink(links, picked, key)
    if (next !== links) focusWhy.current = pairId(picked, key)
    setLinks(next)
    setPicked(null)
  }

  // A new link's reason box takes the focus, so the student writes it at once.
  useEffect(() => {
    if (!focusWhy.current) return
    document.getElementById(`why-${focusWhy.current}`)?.focus()
    focusWhy.current = null
  }, [links])

  useEffect(() => {
    if (!picked) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setPicked(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [picked])

  const send = async () => {
    if (!round || !readyToSend(links) || busy) return
    setBusy('send')
    setError(null)
    try {
      const res = await notebooksAPI.mapBuildSubmit(notebookId, round.id, links)
      setResult({ links: res.data.links, missed: res.data.missed })
    } catch (e) {
      failWith(e)
    } finally {
      setBusy(null)
    }
  }

  const label = (key: string) => round?.concepts.find((c) => c.key === key)?.label ?? key
  const counts = result ? tally(result.links) : null

  return (
    <div className="sheet overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 md:px-5">
        <div className="min-w-0">
          <h2 className="font-display text-lg font-semibold text-slate-900">{t('buildTitle')}</h2>
          <p className="text-sm text-slate-700">
            {result && counts
              ? t('buildScore', { correct: counts.correct, total: result.links.length })
              : t('buildCount', { count: links.length })}
          </p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          <ArrowLeft aria-hidden />
          {t('buildBack')}
        </Button>
      </div>

      {busy === 'start' && !round ? (
        <div className="flex h-72 items-center justify-center gap-2 text-base text-slate-700" aria-busy>
          <Loader2 className="size-5 animate-spin text-mode motion-reduce:animate-none" aria-hidden />
          {t('buildStarting')}
        </div>
      ) : !round ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 px-5 py-6 text-base text-red-700">
          {error || t('failed')}
          <Button type="button" variant="outline" size="sm" onClick={start}>
            {t('retry')}
          </Button>
        </div>
      ) : (
        <div className="md:grid md:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="border-b border-slate-200 p-4 md:border-b-0 md:border-r md:p-5">
            <p className="mb-3 text-sm text-slate-700" aria-live="polite">
              {result ? t('buildResultHint') : picked ? t('buildPickSecond', { label: label(picked) }) : t('buildHint')}
            </p>
            <Board concepts={round.concepts} links={links} result={result} picked={picked} onPress={press} />
          </div>

          <div className="space-y-4 p-4 md:p-5">
            {result ? (
              <ResultList result={result} label={label} />
            ) : links.length === 0 ? (
              <p className="text-sm leading-relaxed text-slate-700">{t('buildEmpty')}</p>
            ) : (
              <ol className="space-y-4">
                {links.map((x) => {
                  const id = pairId(x.from, x.to)
                  return (
                    <li key={id} className="space-y-1.5">
                      <div className="flex items-start justify-between gap-2">
                        <label htmlFor={`why-${id}`} className="text-sm font-semibold text-slate-900">
                          {label(x.from)} — {label(x.to)}
                        </label>
                        <button
                          type="button"
                          onClick={() => setLinks((ls) => removeLink(ls, x.from, x.to))}
                          aria-label={t('buildRemove', { a: label(x.from), b: label(x.to) })}
                          className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                        >
                          <Trash2 className="size-4" aria-hidden />
                        </button>
                      </div>
                      <textarea
                        id={`why-${id}`}
                        rows={2}
                        maxLength={400}
                        value={x.why}
                        placeholder={t('buildWhyPlaceholder')}
                        onChange={(e) => setLinks((ls) => ls.map((y) => (pairId(y.from, y.to) === id ? { ...y, why: e.target.value } : y)))}
                        className="block w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm leading-relaxed text-slate-900 placeholder:text-slate-500 focus-visible:border-mode focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
                      />
                    </li>
                  )
                })}
              </ol>
            )}

            {error !== null && round && <p role="alert" className="text-sm text-red-700">{error || t('failed')}</p>}

            <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-4">
              {result ? (
                <>
                  <Button type="button" onClick={start} disabled={busy !== null}>
                    {busy === 'start' ? <Loader2 className="animate-spin" aria-hidden /> : <RotateCcw aria-hidden />}
                    {t('buildAgain')}
                  </Button>
                  <Button type="button" variant="outline" onClick={onClose}>{t('buildSeeMap')}</Button>
                </>
              ) : (
                <>
                  <Button type="button" onClick={() => void send()} disabled={busy !== null || !readyToSend(links)}>
                    {busy === 'send' ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />}
                    {busy === 'send' ? t('buildSending') : t('buildSend')}
                  </Button>
                  {!readyToSend(links) && links.length > 0 && (
                    <p className="basis-full text-sm text-slate-600">{t('buildNeedWhy')}</p>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** The concepts as cards, with a line for every link: a ring of cards on a
 *  wide screen, two columns on a phone. Lines are drawn between the cards'
 *  measured centres, so they follow whatever the layout is. */
function Board({ concepts, links, result, picked, onPress }: {
  concepts: Concept[]
  links: BuildLink[]
  result: Result | null
  picked: string | null
  onPress: (key: string) => void
}) {
  const t = useTranslations('map')
  const box = useRef<HTMLDivElement>(null)
  const [centres, setCentres] = useState<Record<string, { x: number; y: number }>>({})

  const measure = useCallback(() => {
    const el = box.current
    if (!el) return
    const origin = el.getBoundingClientRect()
    const next: Record<string, { x: number; y: number }> = {}
    el.querySelectorAll<HTMLElement>('[data-build-key]').forEach((card) => {
      const r = card.getBoundingClientRect()
      next[card.dataset.buildKey!] = { x: r.left - origin.left + r.width / 2, y: r.top - origin.top + r.height / 2 }
    })
    setCentres(next)
  }, [])

  useLayoutEffect(() => {
    measure()
    const el = box.current
    if (!el) return
    const watch = new ResizeObserver(measure)
    watch.observe(el)
    return () => watch.disconnect()
  }, [measure, concepts])

  const n = concepts.length
  const drawn = result ? result.links : links.map((x) => ({ ...x, verdict: null as Verdict | null }))
  const linked = new Set(drawn.flatMap((x) => [x.from, x.to]))

  const line = (a: string, b: string) => {
    const p = centres[a]
    const q = centres[b]
    return p && q ? { x1: p.x, y1: p.y, x2: q.x, y2: q.y } : null
  }

  return (
    <div ref={box} className="relative">
      <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
        {result?.missed.map((m) => {
          const at = line(m.from, m.to)
          return at && <line key={`m-${pairId(m.from, m.to)}`} {...at} className="stroke-slate-400" strokeWidth={2} strokeDasharray="6 6" />
        })}
        {drawn.map((x) => {
          const at = line(x.from, x.to)
          return at && (
            <line
              key={pairId(x.from, x.to)}
              {...at}
              strokeWidth={x.verdict ? 3 : 2.5}
              strokeLinecap="round"
              className={x.verdict ? LINE[x.verdict] : 'stroke-mode'}
            />
          )
        })}
      </svg>

      {/* Two columns on a phone; on a wide screen the cards sit on a ring. */}
      <ul className="relative grid grid-cols-2 gap-x-10 gap-y-8 md:block md:aspect-[4/3]" aria-label={t('buildListLabel')}>
        {concepts.map((c, i) => {
          const angle = (2 * Math.PI * i) / n - Math.PI / 2
          const here = picked === c.key
          return (
            <li
              key={c.key}
              className="md:absolute md:left-[var(--x)] md:top-[var(--y)] md:w-[30%] md:-translate-x-1/2 md:-translate-y-1/2"
              style={{ '--x': `${50 + 36 * Math.cos(angle)}%`, '--y': `${50 + 38 * Math.sin(angle)}%` } as React.CSSProperties}
            >
              <button
                type="button"
                data-build-key={c.key}
                onClick={() => onPress(c.key)}
                aria-pressed={here}
                disabled={!!result}
                className={cn(
                  // An opaque card, so a line never shows through it; the tint is a layer inside.
                  'group relative w-full overflow-hidden rounded-lg border bg-white px-3 py-2.5 text-left shadow-sm transition-[border-color,box-shadow] duration-150',
                  'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 disabled:cursor-default motion-reduce:transition-none',
                  here ? 'border-mode ring-2 ring-mode/40' : linked.has(c.key) ? 'border-mode/50' : 'border-slate-300',
                  !result && !here && 'hover:border-mode',
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    'pointer-events-none absolute inset-0 bg-mode/10 transition-opacity duration-150 motion-reduce:transition-none',
                    here ? 'opacity-100' : result ? 'opacity-0' : 'opacity-0 group-hover:opacity-50',
                  )}
                />
                <span className="relative block text-sm font-semibold leading-snug text-slate-900">{c.label}</span>
                <span className="relative mt-0.5 line-clamp-2 text-xs leading-snug text-slate-700">{c.point}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function ResultList({ result, label }: { result: Result; label: (key: string) => string }) {
  const t = useTranslations('map')
  return (
    <div className="space-y-5">
      <ol className="space-y-3">
        {result.links.map((x) => (
          <li key={pairId(x.from, x.to)} className="space-y-1">
            <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900">
              <span className={cn('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium', BADGE[x.verdict])}>
                {x.verdict === 'correct' ? <Check className="size-3.5" aria-hidden /> : x.verdict === 'wrong' ? <X className="size-3.5" aria-hidden /> : null}
                {t(`verdict_${x.verdict}`)}
              </span>
              {label(x.from)} — {label(x.to)}
            </p>
            <p className="text-sm italic leading-relaxed text-slate-700">“{x.why}”</p>
            {x.feedback && <p className="text-sm leading-relaxed text-slate-900">{x.feedback}</p>}
          </li>
        ))}
      </ol>
      {result.missed.length > 0 && (
        <div className="space-y-2 border-t border-slate-200 pt-4">
          <h3 className="text-sm font-semibold text-slate-900">{t('buildMissed', { count: result.missed.length })}</h3>
          <ul className="space-y-2">
            {result.missed.map((m) => (
              <li key={pairId(m.from, m.to)} className="text-sm leading-relaxed">
                <span className="font-medium text-slate-900">{label(m.from)} — {label(m.to)}</span>
                {m.why && <span className="text-slate-700">: {m.why}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs leading-relaxed text-slate-600">{t('buildCounts')}</p>
    </div>
  )
}
