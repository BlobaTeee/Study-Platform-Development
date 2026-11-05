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
