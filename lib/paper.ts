// A paper the student brings to the mock-test page: a photo or a file,
// read once (POST /exercises/read-photo/), then sat whole
// (backend/exercises/services/papers.py).
import type { PhotoQuestion } from './api'

/** Must match photo.max_bytes() in backend/exercises/services/photo.py. */
export const MAX_FILE_BYTES = 15 * 1024 * 1024

export type FileKind = 'image' | 'pdf' | 'docx'

/** What a chosen file is, from its type or, when the browser gives none, its name. */
export function fileKind(file: { type: string; name: string }): FileKind | null {
  const name = file.name.toLowerCase()
  if (file.type.startsWith('image/') || /\.(jpe?g|png|webp|heic|heif)$/.test(name)) return 'image'
  if (file.type === 'application/pdf' || name.endsWith('.pdf')) return 'pdf'
  if (file.type.includes('wordprocessingml') || name.endsWith('.docx')) return 'docx'
  return null
}

export type KindCounts = { choice: number; true_false: number; short: number; written: number }

/** How many questions of each kind the paper holds. */
export function kindCounts(questions: Pick<PhotoQuestion, 'kind'>[]): KindCounts {
  const out: KindCounts = { choice: 0, true_false: 0, short: 0, written: 0 }
  for (const q of questions) out[q.kind ?? 'written'] += 1
  return out
}

/** Whether the file's own answer key covers every question that needs one:
 *  then sitting it asks the AI for nothing more than its written answers. */
export function keyedByFile(questions: Pick<PhotoQuestion, 'kind' | 'answer'>[]): boolean {
  const keyed = questions.filter((q) => q.kind && q.kind !== 'written')
  return keyed.length > 0 && keyed.every((q) => q.answer != null)
}
