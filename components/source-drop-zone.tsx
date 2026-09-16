'use client'

import { cn } from '@/lib/utils'
import { FileUp } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useCallback, useRef, useState, type ReactNode } from 'react'

type SourceDropZoneProps = {
  onFile: (file: File) => void
  disabled?: boolean
  children: ReactNode
  className?: string
}

export function SourceDropZone({
  onFile,
  disabled = false,
  children,
  className,
}: SourceDropZoneProps) {
  const t = useTranslations('notebooks')
  const [active, setActive] = useState(false)
  const depthRef = useRef(0)

  const hasFiles = useCallback((e: React.DragEvent) => {
    return Array.from(e.dataTransfer.types).includes('Files')
  }, [])

  const onDragEnter = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      if (disabled || !hasFiles(e)) return
      depthRef.current += 1
      setActive(true)
    },
    [disabled, hasFiles]
  )

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    depthRef.current = Math.max(0, depthRef.current - 1)
    if (depthRef.current === 0) setActive(false)
  }, [])

  const onDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      if (disabled || !hasFiles(e)) return
      e.dataTransfer.dropEffect = 'copy'
    },
    [disabled, hasFiles]
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      depthRef.current = 0
      setActive(false)
      if (disabled) return
      const file = e.dataTransfer.files?.[0]
      if (file) onFile(file)
    },
    [disabled, onFile]
  )

  return (
    <div
      className={cn('relative flex flex-1 min-h-0 min-w-0', className)}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {children}
      {active && !disabled && (
        <div
          className="absolute inset-0 z-50 flex items-center justify-center rounded-lg m-1 pointer-events-none bg-blue-50/70 backdrop-blur-[1px] border-2 border-dashed border-mode-library/70"
          aria-hidden
        >
          <div className="text-center px-8 py-6 rounded-2xl bg-white border border-mode-library/30 shadow-xl">
            <FileUp className="size-14 text-mode-library mx-auto mb-4" />
            <p className="text-2xl font-semibold text-slate-900">{t('dropToAdd')}</p>
            <p className="text-lg text-slate-500 mt-2">{t('dropFormats')}</p>
          </div>
        </div>
      )}
    </div>
  )
}
