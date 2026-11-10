'use client'

import { useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useState } from 'react'
import { authAPI } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { cn } from '@/lib/utils'
import { LOCALES, writeLocaleCookie, type Locale } from '@/i18n/locale'

/** VI · EN. Each segment names itself in its own language, so a reader who
 *  cannot read the current one can still find theirs. The cookie is written
 *  first — it is what the server renders from — then the profile, when
 *  signed in, so the choice follows the account.
 *
 *  `variant="toggle"` is one square button for places two segments will not
 *  fit (the collapsed sidebar rail): it shows the current code and switches
 *  to the other language on press. */
export function LanguageSwitch({
  compact = false,
  variant = 'segments',
}: {
  compact?: boolean
  variant?: 'segments' | 'toggle'
}) {
  const t = useTranslations('common')
  const locale = useLocale() as Locale
  const router = useRouter()
  const { user } = useAuth()
  const [busy, setBusy] = useState(false)

  const names: Record<Locale, string> = { en: t('english'), vi: t('vietnamese') }
  const short: Record<Locale, string> = { en: 'EN', vi: 'VI' }

  const choose = async (next: Locale) => {
    if (next === locale || busy) return
    setBusy(true)
    writeLocaleCookie(next)
    if (user) {
      try {
        await authAPI.updateProfile({ preferred_language: next })
      } catch {
        /* the cookie still wins locally; the next session re-syncs */
      }
    }
    router.refresh()
    setBusy(false)
  }

  if (variant === 'toggle') {
    const other: Locale = locale === 'en' ? 'vi' : 'en'
    return (
      <button
        type="button"
        onClick={() => void choose(other)}
        title={`${t('language')}: ${names[locale]} → ${names[other]}`}
        aria-label={`${t('language')}: ${names[locale]}`}
        className="grid size-11 place-items-center rounded-lg font-mono text-xs font-semibold uppercase tracking-wide text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-slate-300"
      >
        {short[locale]}
      </button>
    )
  }

  return (
    <div
      role="radiogroup"
      aria-label={t('language')}
      className="inline-flex rounded-md border border-slate-200 bg-white p-0.5"
    >
      {LOCALES.map((code) => {
        const active = code === locale
        return (
          <button
            key={code}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => void choose(code)}
            className={cn(
              'whitespace-nowrap rounded px-2.5 py-1 font-mono text-xs uppercase tracking-wide transition-colors',
              active ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
            )}
            title={names[code]}
          >
            {compact ? (
              short[code]
            ) : (
              <>
                {/* The full name needs room; on a phone the code is enough. */}
                <span className="sm:hidden">{short[code]}</span>
                <span className="hidden sm:inline">{names[code]}</span>
              </>
            )}
          </button>
        )
      })}
    </div>
  )
}
