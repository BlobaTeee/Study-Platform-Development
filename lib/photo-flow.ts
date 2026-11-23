// The photo-or-file flow, as steps the student can see:
// 1 take a photo or choose a file, 2 tick the questions to practise (only
// when there are several), 3 check them and create them as one set.
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

/** Must match MAX_SET in backend/exercises/services/problems.py. */
export const MAX_PICKED = 20

/** The question at `index` ticked or unticked, keeping page order; no more
 *  than `max` can be ticked. */
export function togglePick(picked: number[], index: number, max = MAX_PICKED): number[] {
  if (picked.includes(index)) return picked.filter((i) => i !== index)
  if (picked.length >= max) return picked
  return [...picked, index].sort((a, b) => a - b)
}

/** "Select all" ticks the first `max` questions. */
export function pickAll(count: number, max = MAX_PICKED): number[] {
  return Array.from({ length: Math.min(count, max) }, (_, i) => i)
}

export type FileKind = 'image' | 'pdf' | 'docx'

/** What a chosen file is, from its type or, when the browser gives none, its name. */
export function fileKind(file: { type: string; name: string }): FileKind | null {
  const name = file.name.toLowerCase()
  if (file.type.startsWith('image/') || /\.(jpe?g|png|webp|heic|heif)$/.test(name)) return 'image'
  if (file.type === 'application/pdf' || name.endsWith('.pdf')) return 'pdf'
  if (file.type.includes('wordprocessingml') || name.endsWith('.docx')) return 'docx'
  return null
}
