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
