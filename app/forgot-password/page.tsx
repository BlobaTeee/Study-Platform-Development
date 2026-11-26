'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { useAuth, EMAIL_RATE_LIMIT } from '@/lib/auth-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { AuthBrandPanel } from '@/components/auth-brand-panel'
import { LanguageSwitch } from '@/components/language-switch'

export default function ForgotPasswordPage() {
  const { requestPasswordReset } = useAuth()
  const t = useTranslations('auth')
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await requestPasswordReset(email.trim())
      setSent(true)
    } catch (err) {
      const message = err instanceof Error ? err.message : ''
      setError(message === EMAIL_RATE_LIMIT ? t('emailRateLimit') : message || t('resetRequestFailed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      <AuthBrandPanel />

      <section className="flex items-center justify-center bg-white px-6 py-14">
        <div className="w-full max-w-sm">
          <div className="flex items-start justify-between gap-4 mb-8">
            <div className="lg:hidden">
              <h1 className="font-display text-3xl font-semibold text-slate-900">StudyFlow</h1>
            </div>
            <div className="ml-auto">
              <LanguageSwitch />
            </div>
          </div>
          <h2 className="font-display text-[2rem] font-semibold leading-tight text-slate-900">{t('forgotTitle')}</h2>

          {sent ? (
            // The same message whether or not the address has an account.
            <div className="mt-8 space-y-6">
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
                <p className="text-sm text-emerald-900">{t('resetSent', { email: email.trim() })}</p>
              </div>
              <p className="text-sm text-slate-500">{t('resetSentHint')}</p>
            </div>
          ) : (
            <>
              <p className="text-base text-slate-500 mt-2">{t('forgotLead')}</p>
              <form onSubmit={handleSubmit} className="space-y-4 mt-8">
                {error && (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                    <p className="text-sm text-red-700">{error}</p>
                  </div>
                )}
                <div className="space-y-2">
                  <Label htmlFor="email">{t('email')}</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder={t('emailPlaceholder')}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                    autoFocus
                    required
                  />
                </div>
                <Button
                  type="submit"
                  disabled={loading}
                  size="lg"
                  className="w-full"
                >
                  {loading ? t('sendingResetLink') : t('sendResetLink')}
                </Button>
              </form>
            </>
          )}

          <div className="text-center text-sm text-slate-600 mt-6">
            <Link href="/login" className="font-semibold text-mode-library hover:text-mode-library-hover">
              {t('backToSignIn')}
            </Link>
          </div>
        </div>
      </section>
    </main>
  )
}
