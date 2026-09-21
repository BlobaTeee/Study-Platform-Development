'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { useAuth, type OAuthProvider } from '@/lib/auth-context'

/** "Continue with Google / GitHub" plus the divider that separates them from
 *  the email form. Shared by sign-in and sign-up: with OAuth the two are the
 *  same action, since the account is created on first consent. */
export function OAuthButtons({ onError }: { onError: (message: string) => void }) {
  const t = useTranslations('auth')
  const { loginWithProvider } = useAuth()
  const [pending, setPending] = useState<OAuthProvider | null>(null)

  const go = async (provider: OAuthProvider) => {
    setPending(provider)
    try {
      await loginWithProvider(provider)
      // The browser is leaving for the provider; nothing more to do here.
    } catch (err) {
      onError(err instanceof Error ? err.message : t('oauthFailed'))
      setPending(null)
    }
  }

  return (
    <div className="mt-8">
      <div className="grid gap-3">
        <Button
          type="button"
          variant="outline"
          size="lg"
          disabled={pending !== null}
          onClick={() => void go('google')}
          className="w-full"
        >
          <GoogleMark />
          {t('continueWithGoogle')}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="lg"
          disabled={pending !== null}
          onClick={() => void go('github')}
          className="w-full"
        >
          <GitHubMark />
          {t('continueWithGitHub')}
        </Button>
      </div>
      <div className="flex items-center gap-3 mt-6" aria-hidden>
        <span className="h-px flex-1 bg-slate-200" />
        <span className="text-sm text-slate-500">{t('orDivider')}</span>
        <span className="h-px flex-1 bg-slate-200" />
      </div>
    </div>
  )
}

function GoogleMark() {
  return (
    <svg className="size-5 mr-2" viewBox="0 0 24 24" aria-hidden>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.76h3.57c2.08-1.92 3.27-4.74 3.27-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.76c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.11A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.44.34-2.11V7.05H2.18A11 11 0 0 0 1 12c0 1.78.43 3.45 1.18 4.95l3.66-2.84z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.05l3.66 2.84c.87-2.6 3.3-4.51 6.16-4.51z" />
    </svg>
  )
}

function GitHubMark() {
  return (
    <svg className="size-5 mr-2" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56v-2.17c-3.2.7-3.87-1.36-3.87-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.03 1.76 2.69 1.25 3.35.96.1-.75.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.28 1.18-3.09-.12-.29-.51-1.46.11-3.04 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.62 1.58.23 2.75.11 3.04.74.81 1.18 1.83 1.18 3.09 0 4.41-2.69 5.38-5.26 5.67.41.36.78 1.06.78 2.13v3.16c0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5z" />
    </svg>
  )
}
