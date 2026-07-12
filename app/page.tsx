'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'

export default function Page() {
  const { user, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading) {
      router.replace(user ? '/dashboard/notebooks' : '/login')
    }
  }, [user, loading, router])

  return (
    <main className="flex min-h-screen items-center justify-center bg-white">
      <div className="text-center">
        <div className="animate-spin mb-4">
          <div className="size-10 border-4 border-slate-200 border-t-mode-library rounded-full mx-auto" />
        </div>
        <p className="text-slate-500">Loading...</p>
      </div>
    </main>
  )
}
