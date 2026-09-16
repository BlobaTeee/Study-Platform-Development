export const LOCALES = ['en', 'vi'] as const
export type Locale = (typeof LOCALES)[number]
export const DEFAULT_LOCALE: Locale = 'en'
export const LANG_COOKIE = 'lang'

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (LOCALES as readonly string[]).includes(value)
}

/** Best match for an Accept-Language header, or the default. */
export function localeFromAcceptLanguage(header: string | null | undefined): Locale {
  for (const part of (header ?? '').split(',')) {
    const tag = part.trim().split(';')[0].toLowerCase()
    if (tag.startsWith('vi')) return 'vi'
    if (tag.startsWith('en')) return 'en'
  }
  return DEFAULT_LOCALE
}

// Client-side cookie access. The cookie is the one thing the server reads
// to pick the language, so writing it is how the switch takes effect.
export function readLocaleCookie(): Locale | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(new RegExp(`(?:^|; )${LANG_COOKIE}=([^;]*)`))
  const value = match?.[1]
  return isLocale(value) ? value : null
}

export function writeLocaleCookie(locale: Locale) {
  if (typeof document === 'undefined') return
  document.cookie = `${LANG_COOKIE}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax`
}
