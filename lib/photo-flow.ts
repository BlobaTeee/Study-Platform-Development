// The photo-of-a-problem flow, as steps the student can see:
// 1 take the photo, 2 choose a question (only when the page has several),
// 3 check it against the photo and create the problem.
import type { PhotoQuestion } from './api'

export type PhotoStep = 1 | 2 | 3

export function photoStep({ questionCount, picking }: { questionCount: number; picking: boolean }): PhotoStep {
  if (questionCount === 0) return 1
  return picking ? 2 : 3
}

/** The question as the student will create it, its section's instruction first. */
export function asProblem(q: PhotoQuestion): string {
  return q.instruction ? `${q.instruction}\n${q.text}` : q.text
}
