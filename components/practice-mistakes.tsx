'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import type { PracticeMistakes } from '@/lib/api'

/** Errors made in practice problems, one line per notebook, by kind of
 *  error. Each kind opens the latest problem it was made in. */
export function PracticeMistakesList({ notebooks }: { notebooks: PracticeMistakes[] }) {
  const t = useTranslations('practice')
  return (
    <ul className="mt-3 divide-y divide-slate-100">
      {notebooks.map((nb) => (
        <li key={nb.notebook_id} className="flex flex-col gap-1.5 py-3 sm:flex-row sm:items-baseline sm:gap-6">
          <p className="w-40 shrink-0 truncate text-base text-slate-900">{nb.title}</p>
          <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {nb.types.map((k) => (
              <Link
                key={k.type}
                href={`/dashboard/practice/${k.exercise_ids[k.exercise_ids.length - 1]}`}
                className="rounded text-slate-700 underline-offset-4 hover:text-slate-900 hover:underline focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30"
              >
                {t(`error_${k.type}`)} <span className="font-mono text-xs tabular-nums text-slate-500">{t('mistakeCount', { count: k.count })}</span>
              </Link>
            ))}
          </p>
        </li>
      ))}
    </ul>
  )
}
