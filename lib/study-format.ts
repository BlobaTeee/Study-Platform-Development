/** How much study the schedule says is owed. Counts only — the questions
 *  themselves belong on the study page, since reading one here would be a free
 *  look at a card minutes before you grade your own recall of it. */
export type Due = {
  due: number
  overdue: number
  new: number
  next_date: string | null
  next_count: number
  /** Today's share of the queue: what the day's allowance leaves room for. */
  today?: number
  /** Due cards that did not fit today; they lead tomorrow's queue. */
  later?: number
  /** New cards held back because more is owed than today can clear. */
  new_paused?: boolean
  /** Every test this week whose notebook the queue puts first, soonest first. */
  exams_first?: ExamFirst[]
}

export type ExamFirst = { notebook_id: number; title: string; days: number }

/** Tests grouped by how far away they are, soonest first: several subjects on
 *  one day read as one line ("Biology and Chemistry — test in 3 days"), not
 *  as a repeated sentence per subject. Titles are joined the way the locale
 *  joins a list. */
export function examGroups(exams: ExamFirst[], locale: string): { titles: string; days: number }[] {
  const byDay = new Map<number, string[]>()
  for (const e of exams) byDay.set(e.days, [...(byDay.get(e.days) ?? []), e.title])
  const list = new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' })
  return [...byDay.entries()]
    .sort(([a], [b]) => a - b)
    .map(([days, titles]) => ({ titles: list.format(titles), days }))
}

/** The shape of next-intl's `t` these helpers need: a key under `common`
 *  and its values. Passed in rather than imported so this file stays a
 *  plain module the pages can call from anywhere. */
export type CommonT = (key: string, values?: Record<string, string | number>) => string

/** What the ready-to-study number is made of, worst news first. */
export function dueBreakdown(d: Due, t: CommonT): string {
  const parts: string[] = []
  if (d.overdue) parts.push(t('overdueCount', { count: d.overdue }))
  if (d.due) parts.push(t('dueCount', { count: d.due }))
  if (d.new) parts.push(t('newCount', { count: d.new }))
  return parts.join(' · ')
}

/** An empty queue is the schedule working. Saying only "nothing due" makes that
 *  read exactly like a schedule that's broken, so name the day cards return. */
export function caughtUpMessage(d: Due, t: CommonT, locale: string): string {
  // Today's share is done but debt remains: say so, rather than "caught up".
  if (d.later) {
    return t('doneForToday', { cards: t('cards', { count: d.later }) })
  }
  if (!d.next_date || d.next_count === 0) {
    return t('nothingToStudy')
  }
  const when = new Date(`${d.next_date}T00:00:00`)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = Math.round((when.getTime() - today.getTime()) / 86_400_000)
  const label =
    days === 1
      ? t('tomorrow')
      : t('onDate', { date: when.toLocaleDateString(locale, { day: 'numeric', month: 'short' }) })
  return t('caughtUp', { cards: t('cards', { count: d.next_count }), when: label })
}

/** How well something is known, in words rather than a percentage. A student
 *  reads "Still shaky" at a glance; 47.3% needs working out. The thresholds
 *  are the ones the bar colours use, so word and colour always agree. */
export type MasteryLevel = 'strong' | 'good' | 'shaky' | 'weak'

export function masteryLevel(pct: number): MasteryLevel {
  if (pct >= 85) return 'strong'
  if (pct >= 60) return 'good'
  if (pct >= 40) return 'shaky'
  return 'weak'
}

export const MASTERY_LABEL: Record<MasteryLevel, string> = {
  strong: 'masteryStrong',
  good: 'masteryGood',
  shaky: 'masteryShaky',
  weak: 'masteryWeak',
}

export function masteryBarClass(level: MasteryLevel): string {
  return level === 'weak' ? 'bg-red-400' : level === 'shaky' ? 'bg-mode-flashcards' : 'bg-mode-analytics'
}

/** A 0-100 score on the 10-point scale Vietnamese students are marked on,
 *  with the locale's decimal mark ("7,2" in Vietnamese, "7.2" in English). */
export function scoreOutOfTen(pct: number, locale: string): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(pct / 10)
}
