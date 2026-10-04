import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** Every page opens the same way: the section's colour as a rule, the
 *  title in the display face, one line of lead, and the page's one action
 *  on the right. No label above the title: the rule and the sidebar already
 *  say where you are. */
export function PageHeader({
  title,
  lead,
  meta,
  action,
  className,
}: {
  title: ReactNode
  lead?: ReactNode
  /** A short figure under the title, e.g. "3 of 26". Numbers only. */
  meta?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <header className={cn('mode-rule flex flex-wrap items-end justify-between gap-x-6 gap-y-3 pt-5', className)}>
      <div className="min-w-0 max-w-[65ch]">
        <h1 className="font-display text-[1.75rem] font-semibold leading-tight text-slate-900 md:text-[2rem] text-balance">
          {title}
        </h1>
        {meta && <p className="mt-1 font-mono text-sm text-slate-600 tabular-nums">{meta}</p>}
        {lead && <p className="mt-2 text-base leading-relaxed text-slate-600">{lead}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </header>
  )
}
