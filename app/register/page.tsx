'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth, EMAIL_RATE_LIMIT } from '@/lib/auth-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import Link from 'next/link'
import { Mail } from 'lucide-react'
import { AuthBrandPanel } from '@/components/auth-brand-panel'
import { LanguageSwitch } from '@/components/language-switch'
import { OAuthButtons } from '@/components/oauth-buttons'
import { useTranslations } from 'next-intl'

export default function RegisterPage() {
  const router = useRouter()
  const { register } = useAuth()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [sentTo, setSentTo] = useState('')
  const t = useTranslations('auth')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (password !== confirmPassword) {
      setError(t('passwordsMismatch'))
      return
    }

    setLoading(true)

    try {
      const { needsConfirmation, alreadyRegistered } = await register(username, email, password)
      if (alreadyRegistered) {
        setError(t('alreadyRegistered'))
      } else if (needsConfirmation) {
        setSentTo(email)
      } else {
        router.push('/dashboard/notebooks')
      }
    } catch (err: any) {
      setError(err.message === EMAIL_RATE_LIMIT ? t('emailRateLimit') : err.message || t('registerFailed'))
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

          {sentTo ? (
            <div className="rise">
              <div className="flex size-12 items-center justify-center rounded-full bg-mode-library/10">
                <Mail className="size-6 text-mode-library" />
              </div>
              <h2 className="font-display text-[2rem] font-semibold leading-tight text-slate-900 mt-5">
                {t('checkEmail')}
              </h2>
              <p className="text-base text-slate-600 mt-2 leading-relaxed">
                {t.rich('sentConfirmation', {
                  email: sentTo,
                  b: (chunks) => <span className="font-semibold text-slate-900">{chunks}</span>,
                })}
              </p>
              <Button
                onClick={() => router.push('/login')}
                size="lg"
                className="w-full mt-8"
              >
                {t('goToSignIn')}
              </Button>
              <p className="text-center text-sm text-slate-600 mt-6">
                {t('wrongAddress')}{' '}
                <button
                  type="button"
                  onClick={() => setSentTo('')}
                  className="font-semibold text-mode-library hover:text-mode-library-hover"
                >
                  {t('startOver')}
                </button>
              </p>
            </div>
          ) : (
          <>
          <h2 className="font-display text-[2rem] font-semibold leading-tight text-slate-900">
            {t('createTitle')}
          </h2>
          <p className="text-base text-slate-500 mt-2">
            {t('createLead')}
          </p>

          <OAuthButtons onError={setError} />

          <form onSubmit={handleSubmit} className="space-y-4 mt-6">
            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="username">{t('username')}</Label>
              <Input
                id="username"
                type="text"
                placeholder={t('usernamePlaceholder')}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </div>

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
              <Label htmlFor="password">{t('password')}</Label>
              <PasswordInput
                id="password"
                placeholder={t('createPasswordPlaceholder')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirm-password">{t('confirmPassword')}</Label>
              <PasswordInput
                id="confirm-password"
                placeholder={t('confirmPasswordPlaceholder')}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            <Button
              type="submit"
              disabled={loading}
              size="lg"
              className="w-full"
            >
              {loading ? t('creatingAccount') : t('createAccount')}
            </Button>
          </form>

          <div className="text-center text-sm text-slate-600 mt-6">
            {t('haveAccount')}{' '}
            <Link href="/login" className="font-semibold text-mode-library hover:text-mode-library-hover">
              {t('signIn')}
            </Link>
          </div>
          </>
          )}
        </div>
      </section>
    </main>
  )
}
