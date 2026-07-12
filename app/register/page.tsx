'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Link from 'next/link'
import { Mail } from 'lucide-react'
import { AuthBrandPanel } from '@/components/auth-brand-panel'

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setLoading(true)

    try {
      const { needsConfirmation } = await register(username, email, password)
      if (needsConfirmation) {
        setSentTo(email)
      } else {
        router.push('/dashboard/notebooks')
      }
    } catch (err: any) {
      setError(err.message || 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      <AuthBrandPanel />

      <section className="flex items-center justify-center bg-white px-6 py-14">
        <div className="w-full max-w-sm">
          <div className="lg:hidden mb-8">
            <h1 className="font-display text-3xl font-semibold text-slate-900">StudyFlow</h1>
            <p className="font-mono text-xs uppercase tracking-[0.14em] text-slate-500 mt-1">
              Study workspace
            </p>
          </div>

          {sentTo ? (
            <div className="rise">
              <div className="flex size-12 items-center justify-center rounded-full bg-mode-library/10">
                <Mail className="size-6 text-mode-library" />
              </div>
              <h2 className="font-display text-3xl font-semibold text-slate-900 mt-5">
                Check your email
              </h2>
              <p className="text-base text-slate-600 mt-2 leading-relaxed">
                We sent a confirmation link to{' '}
                <span className="font-semibold text-slate-900">{sentTo}</span>. Open it to
                activate your account, then sign in.
              </p>
              <Button
                onClick={() => router.push('/login')}
                size="lg"
                className="w-full mt-8 font-semibold bg-mode-library hover:bg-mode-library-hover"
              >
                Go to sign in
              </Button>
              <p className="text-center text-sm text-slate-600 mt-6">
                Wrong address?{' '}
                <button
                  type="button"
                  onClick={() => setSentTo('')}
                  className="font-semibold text-mode-library hover:text-mode-library-hover"
                >
                  Start over
                </button>
              </p>
            </div>
          ) : (
          <>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-library">
            Get started
          </p>
          <h2 className="font-display text-3xl font-semibold text-slate-900 mt-1">
            Create your account
          </h2>
          <p className="text-base text-slate-500 mt-2">
            Organize each subject into its own notebook.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4 mt-8">
            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                type="text"
                placeholder="Choose a username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@university.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="Create a password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirm-password">Confirm password</Label>
              <Input
                id="confirm-password"
                type="password"
                placeholder="Re-enter your password"
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
              className="w-full font-semibold bg-mode-library hover:bg-mode-library-hover"
            >
              {loading ? 'Creating account…' : 'Create account'}
            </Button>
          </form>

          <div className="text-center text-sm text-slate-600 mt-6">
            Already have an account?{' '}
            <Link href="/login" className="font-semibold text-mode-library hover:text-mode-library-hover">
              Sign in
            </Link>
          </div>
          </>
          )}
        </div>
      </section>
    </main>
  )
}
