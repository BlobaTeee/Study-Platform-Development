/** The fourteen-day calendar on the Progress page: what one day holds, and
 *  how it is said in words. Kept apart from the component so the rules
 *  (what makes a day studied, which parts are mentioned) can be tested. */

export type ActivityDay = {
  date: string // ISO date, the student's own day
  reviews: number
  correct: number
  accuracy: number | null
  mock_scores: number[]
  quiz_scores?: number[]
  problems?: number
  solved?: number
  explained?: number
  live?: number
}

export type ActivitySummary = {
  days?: number
  reviews: number
  correct?: number
  accuracy: number | null
  mock_tests: number
  quizzes?: number
  problems?: number
  explained?: number
  live?: number
}

/** A message key and its values, turned into text by the caller's `t`. */
export type Line = { key: string; values: Record<string, number> }

/** Anything at all done that day: cards, a quiz, a problem, a mock test,
 *  an explanation or a live round. */
export function studied(day: ActivityDay): boolean {
  return day.reviews > 0 || day.mock_scores.length > 0 || (day.quiz_scores?.length ?? 0) > 0
    || (day.problems ?? 0) > 0 || (day.explained ?? 0) > 0 || (day.live ?? 0) > 0
}

/** The fortnight in short parts, most common activity first, leaving out
 *  what was not done: "12 cards · 2 quizzes · 3 practice problems". */
export function summaryParts(s: ActivitySummary): Line[] {
  const parts: [string, number][] = [
    ['partCards', s.reviews],
    ['partQuizzes', s.quizzes ?? 0],
    ['partProblems', s.problems ?? 0],
    ['partMocks', s.mock_tests],
    ['partExplained', s.explained ?? 0],
    ['partLive', s.live ?? 0],
  ]
  return parts.filter(([, n]) => n > 0).map(([key, count]) => ({ key, values: { count } }))
}

/** One line per thing done that day, in the same order as the summary;
 *  each quiz and mock test is its own line so its score can be read. Scores
 *  stay as percentages here; the caller says them out of ten. */
export function dayLines(day: ActivityDay): Line[] {
  const lines: Line[] = []
  if (day.reviews > 0) {
    lines.push({ key: 'dayCards', values: { cards: day.reviews, recalled: day.correct, forgot: day.reviews - day.correct } })
  }
  for (const score of day.quiz_scores ?? []) lines.push({ key: 'dayQuiz', values: { score } })
  if ((day.problems ?? 0) > 0) lines.push({ key: 'dayProblems', values: { count: day.problems!, solved: day.solved ?? 0 } })
  for (const score of day.mock_scores) lines.push({ key: 'dayMock', values: { score } })
  if ((day.explained ?? 0) > 0) lines.push({ key: 'dayExplained', values: { count: day.explained! } })
  if ((day.live ?? 0) > 0) lines.push({ key: 'dayLive', values: { count: day.live! } })
  return lines
}
