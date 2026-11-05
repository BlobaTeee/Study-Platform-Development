/** Where each concept card sits on the knowledge map. Deterministic, so the
 *  map looks the same every visit: prerequisites to the left, what depends
 *  on them further right, each layer staggered so the whole reads as a
 *  network rather than columns. A layer taller than MAX_ROWS wraps into
 *  extra columns, so forty unlinked concepts do not make one tall strip.
 *  A concept listed twice is placed once, and a link that would close a
 *  cycle is ignored (links are read in the order given), so the layers do
 *  not depend on the order of the keys. */
export const CARD_W = 240
export const CARD_H = 136
const GAP_X = 96
const GAP_Y = 36

export type CardSize = { w: number; h: number; gapX: number; gapY: number }
export const FULL_CARD: CardSize = { w: CARD_W, h: CARD_H, gapX: GAP_X, gapY: GAP_Y }
/** One document's map inside its page: a name and a state dot, no numbers. */
export const SMALL_CARD: CardSize = { w: 176, h: 56, gapX: 120, gapY: 36 }
const MAX_ROWS = 6

export function layoutMap(
  allKeys: string[],
  edges: { from: string; to: string }[],
  size: CardSize = FULL_CARD,
): Record<string, { x: number; y: number }> {
  const keys = [...new Set(allKeys)]
  const known = new Set(keys)
  const candidates = edges.filter((e) => known.has(e.from) && known.has(e.to) && e.from !== e.to)
  // Keep a link only if its target cannot already reach its source.
  const links: { from: string; to: string }[] = []
  const reaches = (from: string, to: string): boolean => {
    const stack = [from]
    const visited = new Set<string>()
    while (stack.length) {
      const k = stack.pop()!
      if (k === to) return true
      if (visited.has(k)) continue
      visited.add(k)
      for (const e of links) if (e.from === k) stack.push(e.to)
    }
    return false
  }
  for (const e of candidates) if (!reaches(e.to, e.from)) links.push(e)
  const layer: Record<string, number> = {}
  const depth = (k: string, seen: Set<string>): number => {
    if (layer[k] !== undefined) return layer[k]
    if (seen.has(k)) return 0
    seen.add(k)
    const before = links.filter((e) => e.to === k).map((e) => depth(e.from, seen) + 1)
    layer[k] = before.length ? Math.max(...before) : 0
    return layer[k]
  }
  keys.forEach((k) => depth(k, new Set()))

  // Order within a layer by where its prerequisites sit, so arrows cross less.
  // A layer that wraps puts the concepts that lead on in its last column, the
  // one next to what they lead to, so their arrows do not run under the
  // layer's other cards; the short column goes first.
  const layers: string[][] = []
  for (const k of keys) (layers[layer[k]] ??= []).push(k)
  const rowOf: Record<string, number> = {}
  const firstChunk = (n: number) => n % MAX_ROWS || MAX_ROWS
  layers.forEach((ks, li) => {
    if (li > 0) {
      const bary = (k: string) => {
        const ps = links.filter((e) => e.to === k).map((e) => rowOf[e.from] ?? 0)
        return ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : Number.MAX_SAFE_INTEGER
      }
      ks.sort((a, b) => bary(a) - bary(b) || keys.indexOf(a) - keys.indexOf(b))
    }
    if (ks.length > MAX_ROWS) {
      const leads = (k: string) => (links.some((e) => e.from === k) ? 1 : 0)
      ks.sort((a, b) => leads(a) - leads(b))
    }
    const first = firstChunk(ks.length)
    ks.forEach((k, i) => (rowOf[k] = i < first ? i : (i - first) % MAX_ROWS))
  })

  const pos: Record<string, { x: number; y: number }> = {}
  let column = 0
  layers.forEach((ks) => {
    if (!ks) return
    for (let start = 0, end = firstChunk(ks.length); start < ks.length; start = end, end += MAX_ROWS) {
      const chunk = ks.slice(start, end)
      const stagger = column % 2 ? (size.h + size.gapY) / 2 : 0
      chunk.forEach((k, i) => (pos[k] = { x: column * (size.w + size.gapX), y: stagger + i * (size.h + size.gapY) }))
      column += 1
    }
  })
  return pos
}
