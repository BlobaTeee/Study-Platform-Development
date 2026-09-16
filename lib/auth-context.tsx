'use client'

import { createContext, useContext, useEffect, useState } from 'react'
import { supabase } from './supabase-client'

interface User {
  id: string
  username: string
  email: string
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<{ needsConfirmation: boolean }>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

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
        username:
          sessionUser.user_metadata?.username || sessionUser.email?.split('@')[0] || 'supabase-user',
        email: sessionUser.email || '',
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
          username:
            session.user.user_metadata?.username || session.user.email?.split('@')[0] || 'supabase-user',
          email: session.user.email || '',
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

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
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
