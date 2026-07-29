/** How much study the schedule says is owed. Counts only — the questions
 *  themselves belong on the study page, since reading one here would be a free
 *  look at a card minutes before you grade your own recall of it. */
export type Due = {
  due: number
  overdue: number
  new: number
  next_date: string | null
  next_count: number
}

/** What the ready-to-study number is made of, worst news first. */
export function dueBreakdown(d: Due): string {
  const parts: string[] = []
  if (d.overdue) parts.push(`${d.overdue} overdue`)
  if (d.due) parts.push(`${d.due} due`)
  if (d.new) parts.push(`${d.new} new`)
  return parts.join(' · ')
}

/** An empty queue is the schedule working. Saying only "nothing due" makes that
 *  read exactly like a schedule that's broken, so name the day cards return. */
export function caughtUpMessage(d: Due): string {
  if (!d.next_date || d.next_count === 0) {
    return 'Nothing to study yet — generate flashcards from a notebook to start.'
  }
  const when = new Date(`${d.next_date}T00:00:00`)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = Math.round((when.getTime() - today.getTime()) / 86_400_000)
  const label =
    days === 1
      ? 'tomorrow'
      : `on ${when.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}`
  return `Caught up — nothing due today. ${d.next_count} card${
    d.next_count === 1 ? '' : 's'
  } return ${label}.`
}
