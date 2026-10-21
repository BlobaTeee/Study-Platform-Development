/** Where each concept card sits on the knowledge map. Deterministic, so the
 *  map looks the same every visit: prerequisites to the left, what depends
 *  on them further right, each layer staggered so the whole reads as a
 *  network rather than columns. A layer taller than MAX_ROWS wraps into
 *  extra columns, so forty unlinked concepts do not make one tall strip.
 *  A concept listed twice is placed once, and a link that would close a
 *  cycle is ignored (links are read in the order given), so the layers do
 *  not depend on the order of the keys. */
export const CARD_W = 208
export const CARD_H = 112
const GAP_X = 96
const GAP_Y = 36
const MAX_ROWS = 6

export function layoutMap(
  allKeys: string[],
  edges: { from: string; to: string }[],
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
  const layers: string[][] = []
  for (const k of keys) (layers[layer[k]] ??= []).push(k)
  const rowOf: Record<string, number> = {}
  layers.forEach((ks, li) => {
    if (li > 0) {
      const bary = (k: string) => {
        const ps = links.filter((e) => e.to === k).map((e) => rowOf[e.from] ?? 0)
        return ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : Number.MAX_SAFE_INTEGER
      }
      ks.sort((a, b) => bary(a) - bary(b) || keys.indexOf(a) - keys.indexOf(b))
    }
    ks.forEach((k, i) => (rowOf[k] = i % MAX_ROWS))
  })

  const pos: Record<string, { x: number; y: number }> = {}
  let column = 0
  layers.forEach((ks) => {
    if (!ks) return
    for (let start = 0; start < ks.length; start += MAX_ROWS) {
      const chunk = ks.slice(start, start + MAX_ROWS)
      const stagger = column % 2 ? (CARD_H + GAP_Y) / 2 : 0
      chunk.forEach((k, i) => (pos[k] = { x: column * (CARD_W + GAP_X), y: stagger + i * (CARD_H + GAP_Y) }))
      column += 1
    }
  })
  return pos
}
