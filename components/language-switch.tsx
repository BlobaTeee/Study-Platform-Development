'use client'

import { useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useState } from 'react'
import { authAPI } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { cn } from '@/lib/utils'
import { LOCALES, writeLocaleCookie, type Locale } from '@/i18n/locale'

/** EN · VI. Each segment names itself in its own language, so a reader who
 *  cannot read the current one can still find theirs. The cookie is written
 *  first — it is what the server renders from — then the profile, when
 *  signed in, so the choice follows the account. */
export function LanguageSwitch({ compact = false }: { compact?: boolean }) {
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
