'use client'

import { createContext, useContext, useEffect, useState } from 'react'
import { supabase } from './supabase-client'
import { authAPI } from './api'

interface User {
  id: string
  username: string
  email: string
  /** True when the account has a password (signed up with email), so the
   *  account page can offer to change it. OAuth-only accounts have none. */
  hasPassword: boolean
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<{ needsConfirmation: boolean }>
  logout: () => Promise<void>
  /** Emails a recovery link that lands on /reset-password. Resolves whether or
   *  not the address has an account, so the form cannot be used to find out. */
  requestPasswordReset: (email: string) => Promise<void>
  /** Sets a new password for the session the recovery link opened. */
  updatePassword: (password: string) => Promise<void>
  /** Leaves for the provider's consent page; the browser comes back to `/`
   *  with a session in the URL and the root page routes to the dashboard. */
  loginWithProvider: (provider: OAuthProvider) => Promise<void>
  /** Renames the account (Supabase user metadata; the backend mirrors it). */
  updateDisplayName: (username: string) => Promise<void>
  /** Re-checks the current password before setting the new one. */
  changePassword: (current: string, next: string) => Promise<void>
  /** Deletes everything, then signs out. */
  deleteAccount: () => Promise<void>
}

export type OAuthProvider = 'google' | 'github'

const AuthContext = createContext<AuthContextType | undefined>(undefined)

/** Email sign-ups set `username`; Google and GitHub set `full_name` / `name`
 *  / `user_name` instead. Fall back to the local part of the email. */
function displayName(meta: Record<string, unknown> | undefined, email: string | undefined): string {
  for (const key of ['username', 'full_name', 'name', 'user_name']) {
    const v = meta?.[key]
    if (typeof v === 'string' && v.trim()) return v.trim()
  }
  return email?.split('@')[0] || 'supabase-user'
}

function hasEmailProvider(appMeta: Record<string, unknown> | undefined): boolean {
  const providers = appMeta?.providers
  return Array.isArray(providers) ? providers.includes('email') : appMeta?.provider === 'email'
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const checkAuth = async () => {
    if (!supabase) {
      setLoading(false)
      return
    }

    const { data } = await supabase.auth.getSession()
    const sessionUser = data.session?.user

    if (sessionUser) {
      setUser({
        id: sessionUser.id,
        username: displayName(sessionUser.user_metadata, sessionUser.email),
        email: sessionUser.email || '',
        hasPassword: hasEmailProvider(sessionUser.app_metadata),
      })
    }

    setLoading(false)
  }

  useEffect(() => {
    checkAuth()

    if (!supabase) {
      return
    }

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        setUser({
          id: session.user.id,
          username: displayName(session.user.user_metadata, session.user.email),
          email: session.user.email || '',
          hasPassword: hasEmailProvider(session.user.app_metadata),
        })
      } else {
        setUser(null)
      }
      setLoading(false)
    })

    return () => {
      subscription.unsubscribe()
    }
  }, [])

  const login = async (email: string, password: string) => {
    if (!supabase) {
      throw new Error('Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY.')
    }

    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })

    if (error || !data.user) {
      throw new Error(error?.message || 'Sign-in failed. Your credentials were not accepted.')
    }

    // Don't set loading to false here - let onAuthStateChange handle it
    // This prevents a race condition where the dashboard guard redirects before
    // the Supabase session is fully synchronized
  }

  const register = async (username: string, email: string, password: string) => {
    if (!supabase) {
      throw new Error('Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY.')
    }

    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { username } },
    })

    if (error || !data.user) {
      throw new Error(error?.message || 'Registration failed. Please try again.')
    }

    // When email confirmation is required, signUp returns a user but NO session
    // until the address is verified. Signal that so the UI can prompt the student
    // to check their email instead of redirecting to a dashboard that would just
    // bounce them back to login. (A session present here means auto-confirm is on
    // and onAuthStateChange will complete the sign-in.)
    return { needsConfirmation: !data.session }
  }

  const logout = async () => {
    if (supabase) {
      await supabase.auth.signOut()
    }
    setUser(null)
  }

  const requestPasswordReset = async (email: string) => {
    if (!supabase) {
      throw new Error('Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY.')
    }
    // The link carries a recovery session in its hash; supabase-js picks it
    // up on /reset-password and fires PASSWORD_RECOVERY. The URL must be on
    // the project's redirect allow-list (Authentication → URL Configuration).
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })
    if (error) throw new Error(error.message)
  }

  const updatePassword = async (password: string) => {
    if (!supabase) {
      throw new Error('Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY.')
    }
    const { error } = await supabase.auth.updateUser({ password })
    if (error) throw new Error(error.message)
  }

  const loginWithProvider = async (provider: OAuthProvider) => {
    if (!supabase) {
      throw new Error('Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY.')
    }
    // `redirectTo` must be on the project's redirect allow-list; the
    // provider itself must be enabled under Authentication → Providers.
    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: `${window.location.origin}/` },
    })
    if (error) throw new Error(error.message)
  }

  const updateDisplayName = async (username: string) => {
    if (!supabase) throw new Error('Supabase is not configured.')
    const { error } = await supabase.auth.updateUser({ data: { username } })
    if (error) throw new Error(error.message)
    // USER_UPDATED reaches onAuthStateChange, which refreshes `user`.
  }

  const changePassword = async (current: string, next: string) => {
    if (!supabase || !user) throw new Error('Not signed in.')
    // Supabase does not ask for the old password; re-signing in is the check.
    const { error: bad } = await supabase.auth.signInWithPassword({ email: user.email, password: current })
    if (bad) throw new Error('WRONG_CURRENT_PASSWORD')
    const { error } = await supabase.auth.updateUser({ password: next })
    if (error) throw new Error(error.message)
  }

  const deleteAccount = async () => {
    await authAPI.deleteAccount()
    await logout()
  }

  return (
    <AuthContext.Provider
      value={{
        user, loading, login, register, logout, requestPasswordReset, updatePassword,
        loginWithProvider, updateDisplayName, changePassword, deleteAccount,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
