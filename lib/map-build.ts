// A map the student builds from memory: their own cards, the links between
// them, and what the comparison with the document said. The server checks
// the same rules (backend/notebooks/services/map_building.py).

export type Card = { id: string; label: string; x: number; y: number }
export type BuildLink = { from: string; to: string; why: string }
export type Verdict = 'correct' | 'partial' | 'wrong' | 'unjudged'
export type GradedLink = BuildLink & { verdict: Verdict; feedback: string }
export type MissedLink = { from: string; to: string; why: string }
export type GradedCard = { id: string; label: string; match_key: string | null; match_label: string | null }
export type BuildResult = {
  id: number
  cards: GradedCard[]
  links: GradedLink[]
  missed: MissedLink[]
  missed_points: { label: string; point: string }[]
  recalled: number
  total: number
}

/** Must match the limits in backend/notebooks/services/map_building.py. */
export const MIN_CARDS = 3
/** A document needs this many key points to be redrawn (MIN_POINTS on the server). */
export const MIN_POINTS = 3
export const MAX_CARDS = 20
export const MAX_LABEL = 80
export const MIN_WHY = 3

export function pairId(a: string, b: string): string {
  return [a, b].sort().join('|')
}

const tidy = (label: string) => label.trim().split(/\s+/).join(' ')

/** A card for a concept, unless it is empty or already on the map (any case). */
export function addCard(cards: Card[], label: string, id: string, at: { x: number; y: number }): Card[] {
  const name = tidy(label).slice(0, MAX_LABEL)
  if (!name || cards.length >= MAX_CARDS || cards.some((c) => c.label.toLocaleLowerCase() === name.toLocaleLowerCase())) return cards
  return [...cards, { id, label: name, x: at.x, y: at.y }]
}

export function removeCard(cards: Card[], links: BuildLink[], id: string) {
  return { cards: cards.filter((c) => c.id !== id), links: links.filter((x) => x.from !== id && x.to !== id) }
}

/** A link between two cards, unless it is to itself or already made. */
export function addLink(links: BuildLink[], from: string, to: string): BuildLink[] {
  if (from === to || links.some((x) => pairId(x.from, x.to) === pairId(from, to))) return links
  return [...links, { from, to, why: '' }]
}

export function removeLink(links: BuildLink[], a: string, b: string): BuildLink[] {
  return links.filter((x) => pairId(x.from, x.to) !== pairId(a, b))
}

/** Where a new card goes: the first free slot of a loose grid, row by row.
 *  Every other card in a row sits lower, so cards are never in one straight
 *  line and a link never runs underneath the cards between its ends. */
export function freeSpot(cards: Card[], width: number, size: { w: number; h: number; gapX: number; gapY: number }) {
  const { w, h, gapX, gapY } = size
  const margin = gapX / 2
  const drop = Math.round(h * 0.9)
  const clear = (x: number, y: number) =>
    cards.every((c) => x + w <= c.x || c.x + w <= x || y + h <= c.y || c.y + h <= y)
  const perRow = Math.max(1, Math.floor((width - 2 * margin + gapX) / (w + gapX)))
  for (let row = 0; row < 40; row++) {
    for (let col = 0; col < perRow; col++) {
      const x = margin + col * (w + gapX)
      const y = margin + row * (h + gapY) + (col % 2) * drop
      if (clear(x, y)) return { x, y }
    }
  }
  return { x: margin, y: margin }
}

/** What still stops the map from being sent, the first thing first; null when ready. */
export function blocker(cards: Card[], links: BuildLink[]):
  | { kind: 'cards'; need: number }
  | { kind: 'links' }
  | { kind: 'why'; n: number }
  | null {
  if (cards.length < MIN_CARDS) return { kind: 'cards', need: MIN_CARDS - cards.length }
  if (links.length === 0) return { kind: 'links' }
  const i = links.findIndex((x) => x.why.trim().length < MIN_WHY)
  return i >= 0 ? { kind: 'why', n: i + 1 } : null
}

export function tally(links: { verdict: Verdict }[]): Record<Verdict, number> {
  const out: Record<Verdict, number> = { correct: 0, partial: 0, wrong: 0, unjudged: 0 }
  for (const x of links) out[x.verdict] += 1
  return out
}

/** Each of a document's key points, in order, with the mastery state of the
 *  map concept that holds it (null when no concept does). */
export function keyPointStates<S extends string>(
  concepts: { members: string[]; state: S }[],
  sourceId: number,
  count: number,
): (S | null)[] {
  const state = new Map<string, S>()
  for (const c of concepts) for (const m of c.members) state.set(m, c.state)
  return Array.from({ length: count }, (_, i) => state.get(`${sourceId}:${i}`) ?? null)
}

export type OutsideNeed<S extends string> = { key: string; label: string; state: S; sourceId: number; title: string }

/** For one document's map: each concept's prerequisites that live in another
 *  document of the notebook, named with that document, so a concept with no
 *  arrow on this map can still say what to understand first. */
export function outsideNeeds<S extends string>(
  concepts: { key: string; label: string; state: S; source_ids: number[] }[],
  edges: { from: string; to: string }[],
  sourceId: number,
  titles: Map<number, string>,
): Record<string, OutsideNeed<S>[]> {
  const byKey = new Map(concepts.map((c) => [c.key, c]))
  const here = (k: string) => byKey.get(k)?.source_ids.includes(sourceId) ?? false
  const out: Record<string, OutsideNeed<S>[]> = {}
  for (const e of edges) {
    const from = byKey.get(e.from)
    if (!from || !here(e.to) || here(e.from)) continue
    const other = from.source_ids.find((s) => s !== sourceId)
    if (other === undefined) continue
    ;(out[e.to] ??= []).push({ key: from.key, label: from.label, state: from.state, sourceId: other, title: titles.get(other) ?? '' })
  }
  return out
}

type Point = { x: number; y: number }

/** Where each link's number sits: the middle of its line, unless another
 *  number is already there (two lines crossing at their middles), in which
 *  case it moves along its own line until it is clear of the others. */
export function spreadBadges(segments: { id: string; a: Point; b: Point }[], gap = 28): Record<string, Point> {
  const placed: Record<string, Point> = {}
  const taken: Point[] = []
  for (const { id, a, b } of segments) {
    const along = (t: number) => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t })
    const clear = (p: Point) => taken.every((q) => Math.hypot(p.x - q.x, p.y - q.y) >= gap)
    const spot = [0.5, 0.35, 0.65, 0.25, 0.75, 0.15, 0.85].map(along).find(clear) ?? along(0.5)
    placed[id] = spot
    taken.push(spot)
  }
  return placed
}
