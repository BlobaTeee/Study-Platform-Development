import { cookies } from 'next/headers'
import { getRequestConfig } from 'next-intl/server'
import { DEFAULT_LOCALE, isLocale, LANG_COOKIE } from './locale'

// No locale routing: the language is a preference, mirrored into a cookie so
// the server can render it from the first byte. Without a choice it is
// Vietnamese, whatever language the browser is set to.
export default getRequestConfig(async () => {
  const cookie = (await cookies()).get(LANG_COOKIE)?.value
  const locale = isLocale(cookie) ? cookie : DEFAULT_LOCALE
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  }
})
