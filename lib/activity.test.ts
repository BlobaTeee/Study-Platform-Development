// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { dayLines, studied, summaryParts, type ActivityDay } from './activity.ts'

const empty: ActivityDay = { date: '2026-11-17', reviews: 0, correct: 0, accuracy: null, mock_scores: [] }

test('a day with only a quiz, a problem, an explanation or a live round is studied', () => {
  assert.equal(studied(empty), false)
  for (const extra of [{ quiz_scores: [80] }, { problems: 1 }, { explained: 1 }, { live: 1 }, { mock_scores: [50] }, { reviews: 1 }]) {
    assert.equal(studied({ ...empty, ...extra }), true, JSON.stringify(extra))
  }
})

test('an older response without the new fields still reads as before', () => {
  assert.equal(studied({ ...empty, reviews: 2, correct: 1 }), true)
  assert.deepEqual(dayLines({ ...empty, reviews: 2, correct: 1 }).map((l) => l.key), ['dayCards'])
})

test('the summary names only what was done, cards first', () => {
  const parts = summaryParts({ reviews: 12, accuracy: 80, mock_tests: 0, quizzes: 2, problems: 3, explained: 0, live: 0 })
  assert.deepEqual(parts, [
    { key: 'partCards', values: { count: 12 } },
    { key: 'partQuizzes', values: { count: 2 } },
    { key: 'partProblems', values: { count: 3 } },
  ])
  assert.deepEqual(summaryParts({ reviews: 0, accuracy: null, mock_tests: 0 }), [])
})

test('a day lists each quiz score on its own line and counts problems once', () => {
  const lines = dayLines({ ...empty, reviews: 12, correct: 10, quiz_scores: [80, 60], problems: 2, solved: 1, mock_scores: [70] })
  assert.deepEqual(lines.map((l) => l.key), ['dayCards', 'dayQuiz', 'dayQuiz', 'dayProblems', 'dayMock'])
  assert.deepEqual(lines[0].values, { cards: 12, recalled: 10, forgot: 2 })
  assert.deepEqual(lines[3].values, { count: 2, solved: 1 })
})
