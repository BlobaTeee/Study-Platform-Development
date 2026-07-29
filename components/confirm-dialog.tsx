'use client'

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

/**
 * An in-app replacement for window.confirm.
 *
 * The browser's own dialog cannot be relied on: Chrome and Safari let a user
 * tick "prevent this page from creating additional dialogs", after which
 * every window.confirm returns false immediately and for good — so a delete
 * button silently stops working while the rest of the page carries on fine,
 * with nothing on screen to explain it. That is not recoverable in code, and
 * it survives a reload.
 *
 * The promise-returning shape is deliberate: it keeps call sites in the same
 * `if (!(await confirm(...))) return` form window.confirm had, so adopting it
 * does not restructure the handlers around it.
 */

export type ConfirmOptions = {
  title: string
  body: string
  confirmLabel?: string
  cancelLabel?: string
  /** Styles the confirm button as destructive. Defaults to true — every
   *  current caller is deleting or discarding something. */
  destructive?: boolean
}

export function useConfirm(): [(options: ConfirmOptions) => Promise<boolean>, ReactNode] {
  const [options, setOptions] = useState<ConfirmOptions | null>(null)
  const resolverRef = useRef<((value: boolean) => void) | null>(null)
  const confirmRef = useRef<HTMLButtonElement>(null)

  const confirm = useCallback((next: ConfirmOptions) => {
    // A second call while one is open would strand the first caller's promise
    // forever, and its `finally` with it — so answer it before replacing it.
    resolverRef.current?.(false)
    setOptions(next)
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve
    })
  }, [])

  const settle = useCallback((value: boolean) => {
    resolverRef.current?.(value)
    resolverRef.current = null
    setOptions(null)
  }, [])

  // Unmounting with a question open (navigating away mid-confirm) must not
  // leave the awaiting handler suspended forever; answering "no" is both the
  // safe reading and the one that lets its `finally` clear loading state.
  useEffect(() => () => resolverRef.current?.(false), [])

  useEffect(() => {
    if (!options) return
    confirmRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') settle(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [options, settle])

  const dialog = options ? (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={() => settle(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-body"
        className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-lift"
        onClick={(event) => event.stopPropagation()}
      >
        <h2
          id="confirm-dialog-title"
          className="font-display text-xl font-semibold text-slate-900"
        >
          {options.title}
        </h2>
        <p id="confirm-dialog-body" className="mt-2 text-base leading-relaxed text-slate-600">
          {options.body}
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="outline" onClick={() => settle(false)}>
            {options.cancelLabel ?? 'Cancel'}
          </Button>
          <Button
            ref={confirmRef}
            type="button"
            onClick={() => settle(true)}
            className={
              options.destructive === false
                ? undefined
                : 'bg-mode-danger text-white hover:bg-mode-danger/90'
            }
          >
            {options.confirmLabel ?? 'Confirm'}
          </Button>
        </div>
      </div>
    </div>
  ) : null

  return [confirm, dialog]
}
