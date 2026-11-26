'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { useAuth } from '@/lib/auth-context'
import { Button } from '@/components/ui/button'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import { AuthBrandPanel } from '@/components/auth-brand-panel'
import { LanguageSwitch } from '@/components/language-switch'

const MIN_PASSWORD = 6 // Supabase's default minimum

/** Where the recovery link lands. supabase-js reads the session out of the
 *  URL hash before this renders, so `user` is set iff the link was valid and
 *  unexpired; without one there is nothing to update and the page says so. */
export default function ResetPasswordPage() {
  const router = useRouter()
  const { user, loading, updatePassword } = useAuth()
  const t = useTranslations('auth')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (password.length < MIN_PASSWORD) {
      setError(t('passwordTooShort', { min: MIN_PASSWORD }))
      return
    }
    if (password !== confirm) {
      setError(t('passwordsMismatch'))
      return
    }
    setSaving(true)
    try {
      await updatePassword(password)
      // The recovery session is a real session: straight in, no second sign-in.
      router.push('/dashboard/notebooks')
    } catch (err) {
      setError(err instanceof Error ? err.message : t('resetFailed'))
      setSaving(false)
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
          <h2 className="font-display text-[2rem] font-semibold leading-tight text-slate-900">{t('resetTitle')}</h2>

          {loading ? (
            <p className="text-base text-slate-500 mt-8">{t('checkingLink')}</p>
          ) : !user ? (
            <div className="mt-8 space-y-6">
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <p className="text-sm text-amber-900">{t('resetLinkInvalid')}</p>
              </div>
              <Button asChild size="lg" className="w-full">
                <Link href="/forgot-password">{t('requestNewLink')}</Link>
              </Button>
            </div>
          ) : (
            <>
              <p className="text-base text-slate-500 mt-2">{t('resetLead', { email: user.email })}</p>
              <form onSubmit={handleSubmit} className="space-y-4 mt-8">
                {error && (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                    <p className="text-sm text-red-700">{error}</p>
                  </div>
                )}
                <div className="space-y-2">
                  <Label htmlFor="password">{t('newPassword')}</Label>
                  <PasswordInput
                    id="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                    autoFocus
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm">{t('confirmPassword')}</Label>
                  <PasswordInput
                    id="confirm"
                    placeholder={t('confirmPasswordPlaceholder')}
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    autoComplete="new-password"
                    required
                  />
                </div>
                <Button
                  type="submit"
                  disabled={saving}
                  size="lg"
                  className="w-full"
                >
                  {saving ? t('savingPassword') : t('savePassword')}
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
