'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { useAuth } from '@/lib/auth-context'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useConfirm } from '@/components/confirm-dialog'
import { AlertCircle, CheckCircle2 } from 'lucide-react'

const MIN_PASSWORD = 6 // Supabase's default minimum

/** The three things a signed-in student needs from an account page: the name
 *  they are called, the password (when they have one), and the way out. */
export default function AccountPage() {
  const t = useTranslations('account')
  const nav = useTranslations('nav')
  const common = useTranslations('common')
  const router = useRouter()
  const { user, updateDisplayName, changePassword, deleteAccount } = useAuth()
  const [confirm, confirmDialog] = useConfirm()

  // Display name — initialised from the session; the Save stays disabled
  // until the field differs from what the account already says.
  const [name, setName] = useState(user?.username ?? '')
  const [nameState, setNameState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  // Password
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [pwError, setPwError] = useState('')
  const [pwState, setPwState] = useState<'idle' | 'saving' | 'saved'>('idle')

  // Deletion
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  if (!user) return null

  const saveName = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed || trimmed === user.username) return
    setNameState('saving')
    try {
      await updateDisplayName(trimmed)
      setNameState('saved')
    } catch {
      setNameState('error')
    }
  }

  const savePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setPwError('')
    if (next.length < MIN_PASSWORD) {
      setPwError(t('passwordTooShort', { min: MIN_PASSWORD }))
      return
    }
    if (next !== again) {
      setPwError(t('passwordsMismatch'))
      return
    }
    setPwState('saving')
    try {
      await changePassword(current, next)
      setPwState('saved')
      setCurrent('')
      setNext('')
      setAgain('')
    } catch (err) {
      setPwState('idle')
      const msg = err instanceof Error ? err.message : ''
      setPwError(msg === 'WRONG_CURRENT_PASSWORD' ? t('wrongCurrentPassword') : msg || t('passwordFailed'))
    }
  }

  const removeAccount = async () => {
    const ok = await confirm({
      title: t('deleteTitle'),
      body: t('deleteBody', { email: user.email }),
      confirmLabel: t('deleteConfirm'),
      cancelLabel: common('cancel'),
    })
    if (!ok) return
    setDeleting(true)
    setDeleteError('')
    try {
      await deleteAccount()
      router.replace('/login')
    } catch {
      setDeleteError(t('deleteFailed'))
      setDeleting(false)
    }
  }


  return (
    <div className="max-w-2xl mx-auto space-y-8">
      {confirmDialog}
      <div className="mode-rule pt-5">
        <h1 className="font-display text-[2rem] font-semibold leading-tight text-slate-900">{nav('account')}</h1>
        <p className="mt-2 text-base text-slate-600">{user.email}</p>
      </div>

      {/* Name */}
      <Card className="p-6 md:p-8">
        <form onSubmit={saveName} className="space-y-4">
          <div>
            <h2 className="font-display text-xl font-semibold text-slate-900">{t('nameTitle')}</h2>
            <p className="text-sm text-slate-500 mt-1">{t('nameLead')}</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="name">{t('nameLabel')}</Label>
            <Input
              id="name"
              value={name}
              maxLength={60}
              onChange={(e) => {
                setName(e.target.value)
                if (nameState !== 'idle') setNameState('idle')
              }}
             
            />
          </div>
          <div className="flex items-center gap-3">
            <Button
              type="submit"
              size="lg"
              disabled={nameState === 'saving' || !name.trim() || name.trim() === user.username}
              variant="ink"
            >
              {common('save')}
            </Button>
            {nameState === 'saved' && (
              <span className="inline-flex items-center gap-1.5 text-sm text-emerald-700">
                <CheckCircle2 className="size-4" aria-hidden /> {t('saved')}
              </span>
            )}
            {nameState === 'error' && <span className="text-sm text-red-700">{t('nameFailed')}</span>}
          </div>
        </form>
      </Card>

      {/* Password — only for accounts that have one */}
      <Card className="p-6 md:p-8">
        <div>
          <h2 className="font-display text-xl font-semibold text-slate-900">{t('passwordTitle')}</h2>
          <p className="text-sm text-slate-500 mt-1">
            {user.hasPassword ? t('passwordLead') : t('passwordOAuthOnly')}
          </p>
        </div>
        {user.hasPassword && (
          <form onSubmit={savePassword} className="space-y-4 mt-5">
            <div className="space-y-2">
              <Label htmlFor="current">{t('currentPassword')}</Label>
              <Input id="current" type="password" autoComplete="current-password" value={current}
                     onChange={(e) => setCurrent(e.target.value)} required />
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="next">{t('newPassword')}</Label>
                <Input id="next" type="password" autoComplete="new-password" value={next}
                       onChange={(e) => setNext(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="again">{t('confirmPassword')}</Label>
                <Input id="again" type="password" autoComplete="new-password" value={again}
                       onChange={(e) => setAgain(e.target.value)} required />
              </div>
            </div>
            {pwError && (
              <div className="flex gap-3 rounded-lg bg-red-50 p-3 border border-red-200">
                <AlertCircle className="size-5 text-mode-danger shrink-0" />
                <p className="text-sm text-red-700">{pwError}</p>
              </div>
            )}
            <div className="flex items-center gap-3">
              <Button type="submit" size="lg" disabled={pwState === 'saving'} variant="ink">
                {t('changePassword')}
              </Button>
              {pwState === 'saved' && (
                <span className="inline-flex items-center gap-1.5 text-sm text-emerald-700">
                  <CheckCircle2 className="size-4" aria-hidden /> {t('passwordSaved')}
                </span>
              )}
            </div>
          </form>
        )}
      </Card>

      {/* Deletion */}
      <Card className="border-red-200 p-6 md:p-8">
        <h2 className="font-display text-xl font-semibold text-slate-900">{t('deleteSection')}</h2>
        <p className="text-sm text-slate-500 mt-1">{t('deleteLead')}</p>
        {deleteError && <p className="text-sm text-red-700 mt-3">{deleteError}</p>}
        <Button
          type="button"
          size="lg"
          variant="outline"
          disabled={deleting}
          onClick={() => void removeAccount()}
          className="mt-5 self-start border-red-300 text-red-700 hover:bg-red-50"
        >
          {deleting ? t('deleting') : t('deleteButton')}
        </Button>
      </Card>
    </div>
  )
}
