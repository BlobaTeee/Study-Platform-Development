/** A document keeps its own language; the page asks for its texts in the
 *  page language (POST /notebooks/translate/). These are the pure parts. */

/** The server's limit on texts per request. */
export const MAX_TEXTS = 100

/** A text to translate. A short answer comes with its question (`context`):
 *  alone it is a word without a sense ("Force" → "Buộc"). */
export type Ask = string | { text: string; context: string }

/** Where a translation is found: the text, or the text under its question. */
export function askKey(ask: Ask): string {
  return typeof ask === 'string' ? ask : `${ask.context}\u0000${ask.text}`
}

const textOf = (ask: Ask) => (typeof ask === 'string' ? ask : ask.text)

/** The texts worth asking for: each once, no blanks. */
export function toAsk(asks: (Ask | undefined | null)[]): Ask[] {
  const seen = new Map<string, Ask>()
  for (const a of asks) if (a && textOf(a).trim() && !seen.has(askKey(a))) seen.set(askKey(a), a)
  return [...seen.values()]
}

/** A short answer: four words at most, not a sentence. */
export function isShort(text: string): boolean {
  return text.trim().split(/\s+/).length <= 4 && !/[.!?]$/.test(text.trim())
}

/** `answer` as worth asking: with its question when it is short. */
function answerTo(answer: string | undefined, question: string): Ask | undefined {
  if (!answer) return undefined
  return isShort(answer) ? { text: answer, context: question } : answer
}

/** A flashcard's texts: its question, its answer, its explanation. */
export function cardTexts(card: { question: string; answer: string; explanation?: string }): Ask[] {
  return toAsk([card.question, answerTo(card.answer, card.question), card.explanation])
}

/** A quiz question's texts. True and False are shown in the page's words already. */
export function quizTexts(q: { question_text: string; options?: string[]; explanation?: string | null }): Ask[] {
  const choices = (q.options ?? []).filter((o) => o !== 'True' && o !== 'False')
  return toAsk([q.question_text, ...choices.map((o) => answerTo(o, q.question_text)), q.explanation])
}

export function batches<T>(items: T[], size: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size))
  return out
}

/** What to show instead of `text` (asked under `context`), or undefined to show it as it is. */
export function shownAs(found: Map<string, string> | undefined, text: string, context?: string): string | undefined {
  const t = found?.get(context === undefined ? text : askKey({ text, context }))
  return t && t.toLowerCase() !== text.toLowerCase() ? t : undefined
}

type MapLike = {
  concepts: { key: string; label: string; point: string; source_ids: number[] }[]
  edges: { from: string; to: string; why: string }[]
}

/** The map's texts worth translating. In a document's page: every name (a
 *  prerequisite from another document is named too), but only this
 *  document's points and the reasons for links into it. */
export function mapTexts(map: MapLike, sourceId?: number): Ask[] {
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

/** What a quiz's stored name says it is from: the server writes it in English
 *  ("Quiz: Energy and waves", "Quiz: 3 sources"). Null for any other name. */
export function quizTitle(title: string): { name: string } | { count: number } | null {
  const many = title.match(/^Quiz: (\d+) sources$/)
  if (many) return { count: Number(many[1]) }
  return title.startsWith('Quiz: ') ? { name: title.slice('Quiz: '.length) } : null
}
