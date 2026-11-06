/** A document keeps its own language; the page asks for its texts in the
 *  page language (POST /notebooks/translate/). These are the pure parts. */

/** The server's limit on texts per request. */
export const MAX_TEXTS = 100

/** The texts worth asking for: each once, no blanks. */
export function toAsk(texts: (string | undefined | null)[]): string[] {
  return [...new Set(texts.filter((t): t is string => !!t && !!t.trim()))]
}

export function batches<T>(items: T[], size: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size))
  return out
}

/** What to show instead of `text`, or undefined to show it as it is. */
export function shownAs(found: Map<string, string> | undefined, text: string): string | undefined {
  const t = found?.get(text)
  return t && t !== text ? t : undefined
}

type MapLike = {
  concepts: { key: string; label: string; point: string; source_ids: number[] }[]
  edges: { from: string; to: string; why: string }[]
}

/** The map's texts worth translating. In a document's page: every name (a
 *  prerequisite from another document is named too), but only this
 *  document's points and the reasons for links into it. */
export function mapTexts(map: MapLike, sourceId?: number): string[] {
  const here = (c: MapLike['concepts'][number]) => sourceId === undefined || c.source_ids.includes(sourceId)
  const inDoc = new Set(map.concepts.filter(here).map((c) => c.key))
  return toAsk([
    ...map.concepts.map((c) => c.label),
    ...map.concepts.filter(here).map((c) => c.point),
    ...map.edges.filter((e) => inDoc.has(e.to)).map((e) => e.why),
  ])
}

/** The map with its texts in the page language; each translated name keeps
 *  its original in `original`, for hover. The same map while nothing is found. */
export function inPageLanguage<M extends MapLike>(map: M, found: Map<string, string> | undefined): M {
  if (!found?.size) return map
  return {
    ...map,
    concepts: map.concepts.map((c) => {
      const label = shownAs(found, c.label)
      return { ...c, label: label ?? c.label, point: shownAs(found, c.point) ?? c.point, original: label ? c.label : undefined }
    }),
    edges: map.edges.map((e) => ({ ...e, why: shownAs(found, e.why) ?? e.why })),
  }
}
