'use client'

import useSWR from 'swr'
import { useLocale } from 'next-intl'
import { notebooksAPI } from '@/lib/api'
import { batches, MAX_TEXTS, shownAs, toAsk } from '@/lib/translate'

/** A document's texts translated into the page language, as original →
 *  translation. Undefined while loading; the page shows the originals
 *  until then, and for good if the model is not available. */
export function useInPageLanguage(texts: (string | undefined | null)[]): Map<string, string> | undefined {
  const locale = useLocale()
  const asked = toAsk(texts)
  const { data } = useSWR(
    asked.length ? ['/translate', locale, ...asked] : null,
    async () => {
      const found = new Map<string, string>()
      for (const batch of batches(asked, MAX_TEXTS)) {
        const res = await notebooksAPI.translate(batch, locale)
        batch.forEach((text, i) => found.set(text, res.data.translations[i] ?? text))
      }
      return found
    },
    { revalidateOnFocus: false, shouldRetryOnError: false },
  )
  return data
}

/** `text` in the page language when there is a translation, the document's
 *  own words on hover. */
export function InPageLanguage({ text, found }: { text: string; found: Map<string, string> | undefined }) {
  const shown = shownAs(found, text)
  return shown ? <span title={text}>{shown}</span> : <>{text}</>
}
