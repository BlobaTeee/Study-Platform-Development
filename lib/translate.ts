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

/** A short answer inside a sentence of the page: "Lực (Force)", the
 *  document's word kept beside its translation; as written when there is none. */
export function withOriginal(found: Map<string, string> | undefined, text: string, context?: string): string {
  const shown = shownAs(found, text, context)
  return shown ? `${shown} (${text})` : text
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

/** What a quiz's stored name says it is from: the server writes it in English
 *  ("Quiz: Energy and waves", "Quiz: 3 sources"). Null for any other name. */
export function quizTitle(title: string): { name: string } | { count: number } | null {
  const many = title.match(/^Quiz: (\d+) sources$/)
  if (many) return { count: Number(many[1]) }
  return title.startsWith('Quiz: ') ? { name: title.slice('Quiz: '.length) } : null
}
