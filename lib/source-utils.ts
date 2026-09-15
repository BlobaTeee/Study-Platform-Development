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

export function parseSourceIdsParam(param: string | null | undefined): number[] {
  if (!param?.trim()) return []
  return [...new Set(param.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => n > 0))]
}

export function formatSourceIdsForQuery(ids: number[]): string {
  return [...new Set(ids)].sort((a, b) => a - b).join(',')
}

/** Whether an item generated from `itemSourceIds` belongs in a view of
 *  `selected` sources: it must have every one of them. An item from [1, 3]
 *  shows under ?source=1 and under ?source=1,3; an item from [1] does not
 *  show under ?source=1,3. An empty selection matches nothing, which is what
 *  the pages' "pick a document first" guards rely on. */
export function hasAllSources(itemSourceIds: number[] | undefined, selected: number[]): boolean {
  if (!itemSourceIds || selected.length === 0) return false
  return selected.every((id) => itemSourceIds.includes(id))
}
