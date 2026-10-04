import { BarChart3, HelpCircle, NotebookText, Zap } from 'lucide-react'
import { useTranslations } from 'next-intl'

const modes = [
  { label: 'notebooks', icon: NotebookText, tint: 'bg-mode-library/10 text-mode-library' },
  { label: 'flashcards', icon: Zap, tint: 'bg-mode-flashcards/10 text-mode-flashcards' },
  { label: 'quizzes', icon: HelpCircle, tint: 'bg-mode-quizzes/10 text-mode-quizzes' },
  { label: 'analytics', icon: BarChart3, tint: 'bg-mode-analytics/10 text-mode-analytics' },
] as const

/** Left-hand brand story shown beside the auth form on desktop. Teaches the
 *  product's promise and its four color-coded modes before you even sign in. */
export function AuthBrandPanel() {
  const t = useTranslations('auth')
  const nav = useTranslations('nav')
  return (
    <aside className="paper-grid relative hidden lg:flex flex-col justify-between border-r border-slate-200 p-12 xl:p-16">
      <div>
        <p className="font-display text-xl font-semibold text-slate-900">StudyFlow</p>
      </div>

      <div className="max-w-md">
        <h2 className="font-display text-4xl xl:text-5xl font-semibold leading-[1.08] text-slate-900">
          {t('brandHeadline')}
        </h2>
        <p className="mt-5 max-w-[48ch] text-lg leading-relaxed text-slate-600">
          {t('brandLead')}
        </p>
      </div>

      <ul className="grid grid-cols-2 gap-x-6 gap-y-3 max-w-md">
        {modes.map((mode) => {
          const Icon = mode.icon
          return (
            <li key={mode.label} className="flex items-center gap-3">
              <span className={`grid size-8 shrink-0 place-items-center rounded-lg ${mode.tint}`}>
                <Icon className="size-4" />
              </span>
              <span className="text-sm font-medium text-slate-700">{nav(mode.label)}</span>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
