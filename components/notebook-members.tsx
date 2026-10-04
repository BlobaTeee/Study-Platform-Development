'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Check, Copy, Loader2, UserRound } from 'lucide-react'
import { mutate } from 'swr'
import { notebooksAPI, type NotebookMemberRow } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useConfirm } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'

type Invite = { email: string; url: string; emailed: boolean }

/** Who is in a shared notebook, how each of them is doing in it, and the
 *  ways in and out: invite by email, remove, leave. The owner sees the
 *  invite form; a member sees the list and their own way out. */
export function NotebookMembers({ notebookId, onClose }: { notebookId: number; onClose: () => void }) {
  const t = useTranslations('notebooks')
  const common = useTranslations('common')
  const router = useRouter()
  const [confirm, confirmDialog] = useConfirm()

  const [members, setMembers] = useState<NotebookMemberRow[] | null>(null)
  const [email, setEmail] = useState('')
  const [inviting, setInviting] = useState(false)
  const [invite, setInvite] = useState<Invite | null>(null)
  const [copied, setCopied] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [error, setError] = useState('')

  const load = () => {
    notebooksAPI
      .members(notebookId)
      .then((res) => setMembers(res.data.members))
      .catch(() => setError(t('inviteFailed')))
  }

  useEffect(() => {
    let cancelled = false
    notebooksAPI
      .members(notebookId)
      .then((res) => {
        if (!cancelled) setMembers(res.data.members)
      })
      .catch(() => {
        if (!cancelled) setError(t('inviteFailed'))
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notebookId])

  const you = members?.find((m) => m.is_you)
  const youAreOwner = you?.role === 'owner'

  const sendInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    const address = email.trim()
    if (!address || inviting) return
    setInviting(true)
    setError('')
    setCopied(false)
    try {
      const res = await notebooksAPI.invite(notebookId, address)
      setInvite(res.data)
      setEmail('')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail || t('inviteFailed'))
    } finally {
      setInviting(false)
    }
  }

  const copy = async () => {
    if (!invite) return
    try {
      await navigator.clipboard.writeText(invite.url)
      setCopied(true)
    } catch {
      // Clipboard blocked: the link is on screen to copy by hand.
    }
  }

  const remove = async (member: NotebookMemberRow) => {
    const leaving = member.is_you
    const ok = await confirm({
      title: leaving ? t('leaveTitle') : t('removeMemberTitle', { name: member.name }),
      body: leaving ? t('leaveBody') : t('removeMemberBody'),
      confirmLabel: leaving ? t('leaveNotebook') : t('removeMemberAction'),
      cancelLabel: common('cancel'),
    })
    if (!ok) return
    setBusyId(member.user_id)
    setError('')
    try {
      await notebooksAPI.removeMember(notebookId, member.user_id)
      if (leaving) {
        mutate(['/notebooks/'])
        router.push('/dashboard/notebooks')
        return
      }
      load()
    } catch {
      setError(t('inviteFailed'))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="border-b border-slate-200 bg-slate-50 px-5 py-5 md:px-6" aria-label={t('membersTitle')}>
      {confirmDialog}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-slate-900">{t('membersTitle')}</h2>
          <p className="mt-1 max-w-[60ch] text-sm text-slate-600">{t('membersLead')}</p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          {common('close')}
        </Button>
      </div>

      {members === null ? (
        <div className="mt-4 h-12 animate-pulse rounded-lg bg-slate-200/60 motion-reduce:animate-none" aria-busy />
      ) : (
        <ul className="mt-4 divide-y divide-slate-200 border-y border-slate-200 bg-white">
          {members.map((m) => (
            <li key={m.user_id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
              <span className="grid size-8 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-500">
                <UserRound className="size-4" aria-hidden />
              </span>
              <div className="min-w-0 flex-1 basis-48">
                <p className="truncate text-[15px] font-medium text-slate-900">
                  {m.name}
                  {m.is_you && <span className="ml-1.5 font-normal text-slate-500">({t('you')})</span>}
                </p>
                <p className="truncate text-sm text-slate-600">
                  {m.role === 'owner' ? t('roleOwner') : t('roleMember')} ·{' '}
                  {t('memberRecord', { reviews: m.reviews })}
                  {m.accuracy != null ? t('memberAccuracy', { pct: m.accuracy }) : ''}
                </p>
              </div>
              {(m.is_you ? m.role !== 'owner' : youAreOwner) && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={busyId === m.user_id}
                  onClick={() => void remove(m)}
                  className="text-slate-600 hover:bg-red-50 hover:text-mode-danger"
                >
                  {busyId === m.user_id ? <Loader2 className="animate-spin" aria-hidden /> : null}
                  {m.is_you ? t('leaveNotebook') : t('removeMemberAction')}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {youAreOwner && (
        <form onSubmit={sendInvite} className="mt-4 flex flex-wrap items-end gap-3">
          <div className="min-w-0 flex-1 basis-64 space-y-1.5">
            <Label htmlFor="invite-email">{t('inviteLabel')}</Label>
            <Input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t('invitePlaceholder')}
            />
          </div>
          <Button type="submit" disabled={inviting || !email.trim()}>
            {inviting ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t('inviteButton')}
          </Button>
        </form>
      )}

      {invite && (
        <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
          <p className="text-sm text-slate-700">
            {invite.emailed ? t('inviteSent', { email: invite.email }) : t('inviteLinkOnly')}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <code className={cn('min-w-0 flex-1 basis-64 truncate rounded bg-slate-100 px-2 py-1.5 font-mono text-xs text-slate-700')}>
              {invite.url}
            </code>
            <Button type="button" variant="outline" size="sm" onClick={() => void copy()}>
              {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
              {copied ? t('copied') : t('copyLink')}
            </Button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {error}
        </p>
      )}
    </section>
  )
}
