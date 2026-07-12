export type SourceFileType = 'pdf' | 'docx' | 'pptx'

const EXTENSIONS: SourceFileType[] = ['pdf', 'docx', 'pptx']

export const SOURCE_ACCEPT =
  '.pdf,.docx,.pptx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation'

export function isAllowedSourceFile(file: File): boolean {
  const ext = file.name.split('.').pop()?.toLowerCase()
  return ext !== undefined && EXTENSIONS.includes(ext as SourceFileType)
}

export function titleFromFileName(name: string): string {
  return name.replace(/\.(pdf|docx|pptx)$/i, '')
}

export function fileTypeLabel(fileType?: string): string {
  if (fileType === 'docx') return 'Word'
  if (fileType === 'pptx') return 'PowerPoint'
  return 'PDF'
}

export function sourceCountLabel(fileType: string | undefined, pageCount: number): string | null {
  if (!pageCount || pageCount <= 0) return null
  if (fileType === 'pptx') return `${pageCount} slides`
  if (fileType === 'pdf') return `${pageCount} pg`
  return null
}

/** Canonical tag for one or more source IDs, e.g. source:3 or source:1,3,7 */
export function buildSourceTag(sourceIds: number[]): string {
  const sorted = [...new Set(sourceIds)].filter((id) => id > 0).sort((a, b) => a - b)
  return `source:${sorted.join(',')}`
}

export function parseSourceIdsParam(param: string | null | undefined): number[] {
  if (!param?.trim()) return []
  return [...new Set(param.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => n > 0))]
}

export function formatSourceIdsForQuery(ids: number[]): string {
  return [...new Set(ids)].sort((a, b) => a - b).join(',')
}

export function flashcardMatchesSourceTag(tags: string | null | undefined, sourceIds: number[]): boolean {
  if (!tags || sourceIds.length === 0) return false
  const expected = buildSourceTag(sourceIds)
  return tags === expected || tags.includes(expected)
}

export function quizMatchesSourceTag(description: string | null | undefined, sourceIds: number[]): boolean {
  if (!description || sourceIds.length === 0) return false
  const expected = buildSourceTag(sourceIds)
  return description.includes(`[${expected}]`) || description.includes(expected)
}
