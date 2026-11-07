'use client'

import useSWR from 'swr'
import { useLocale } from 'next-intl'
import { notebooksAPI } from '@/lib/api'
import { MathText } from '@/components/math-text'
import { type Ask, askKey, batches, MAX_TEXTS, shownAs, toAsk } from '@/lib/translate'

/** A document's texts translated into the page language, keyed by askKey.
 *  Undefined while loading; the page shows the originals until then, and
 *  for good if the model is not available. */
export function useInPageLanguage(texts: (Ask | undefined | null)[]): Map<string, string> | undefined {
  const locale = useLocale()
  const asked = toAsk(texts)
  const { data } = useSWR(
    asked.length ? ['/translate', locale, ...asked.map(askKey)] : null,
    async () => {
      const found = new Map<string, string>()
      for (const batch of batches(asked, MAX_TEXTS)) {
        const texts = batch.map((a) => (typeof a === 'string' ? a : a.text))
        const contexts = batch.some((a) => typeof a !== 'string')
          ? batch.map((a) => (typeof a === 'string' ? null : a.context))
          : undefined
        const res = await notebooksAPI.translate(texts, locale, contexts)
        batch.forEach((a, i) => found.set(askKey(a), res.data.translations[i] ?? texts[i]))
      }
      return found
    },
    { revalidateOnFocus: false, shouldRetryOnError: false },
  )
  return data
}

/** `text` in the page language when there is a translation, the document's
 *  own words on hover. A short answer (asked with its `context`) keeps its
 *  own words beside it instead: a one-word translation can miss the sense.
 *  `math`: the text may hold $…$ formulas, typeset as MathText does. */
export function InPageLanguage({ text, found, context, math = false }: {
  text: string
  found: Map<string, string> | undefined
  context?: string
  math?: boolean
}) {
  const shown = shownAs(found, text, context)
  const show = (t: string) => (math ? <MathText text={t} /> : t)
  if (!shown) return <>{show(text)}</>
  if (context === undefined) return <span title={text}>{show(shown)}</span>
  return (
    <>
      {show(shown)} <span className="text-[0.8em] font-normal text-slate-500">{show(text)}</span>
    </>
  )
}
