'use client'

import { Suspense, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Link from 'next/link'
import { AuthBrandPanel } from '@/components/auth-brand-panel'
import { LanguageSwitch } from '@/components/language-switch'
import { OAuthButtons } from '@/components/oauth-buttons'
import { useTranslations } from 'next-intl'

function LoginForm() {
  const router = useRouter()
  const { login } = useAuth()
  // Only in-app paths: `next=https://evil.example` must not become a redirect.
  const nextParam = useSearchParams().get('next') ?? ''
  const nextPath = nextParam.startsWith('/') && !nextParam.startsWith('//')
    ? nextParam
    : '/dashboard/notebooks'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const t = useTranslations('auth')
  const nav = useTranslations('nav')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await login(email, password)
      // An invitation link parks its destination in `next` so signing in
      // lands on the notebook you were invited to, not the generic list.
      router.push(nextPath)
    } catch (err: any) {
      setError(err.message || t('loginFailed'))
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
              <p className="font-mono text-xs uppercase tracking-[0.14em] text-slate-500 mt-1">
                {nav('tagline')}
              </p>
            </div>
            <div className="ml-auto">
              <LanguageSwitch />
            </div>
          </div>

          <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-library">
            {t('welcomeBack')}
          </p>
          <h2 className="font-display text-3xl font-semibold text-slate-900 mt-1">
            {t('signInTitle')}
          </h2>
          <p className="text-base text-slate-500 mt-2">
            {t('signInLead')}
          </p>

          <OAuthButtons onError={setError} />

          <form onSubmit={handleSubmit} className="space-y-4 mt-6">
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
                required
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">{t('password')}</Label>
                <Link href="/forgot-password" className="text-sm text-slate-500 hover:text-mode-library">
                  {t('forgotPassword')}
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                placeholder={t('passwordPlaceholder')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            <Button
              type="submit"
              disabled={loading}
              size="lg"
              className="w-full font-semibold bg-mode-library hover:bg-mode-library-hover"
            >
              {loading ? t('signingIn') : t('signIn')}
            </Button>
          </form>

          <div className="text-center text-sm text-slate-600 mt-6">
            {t('noAccount')}{' '}
            <Link href="/register" className="font-semibold text-mode-library hover:text-mode-library-hover">
              {t('createOne')}
            </Link>
          </div>

          <div className="text-center text-xs text-slate-400 mt-4">
            <Link href="/developer" className="hover:text-slate-600 underline underline-offset-4">
              {t('adminLinks')}
            </Link>
          </div>
        </div>
      </section>
    </main>
  )
}

/** useSearchParams needs a boundary, or the whole route opts out of static
 *  rendering and the shell flashes before the form. */
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  )
}
