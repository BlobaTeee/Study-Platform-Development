import { cookies, headers } from 'next/headers'
import { getRequestConfig } from 'next-intl/server'
import { isLocale, localeFromAcceptLanguage, LANG_COOKIE } from './locale'

// No locale routing: the language is a preference, mirrored into a cookie so
// the server can render it from the first byte. Signed-out visitors get
// their browser's language.
export default getRequestConfig(async () => {
  const cookie = (await cookies()).get(LANG_COOKIE)?.value
  const locale = isLocale(cookie)
    ? cookie
    : localeFromAcceptLanguage((await headers()).get('accept-language'))
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  }
})
