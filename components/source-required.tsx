'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { BookMarked, FileText } from 'lucide-react'

export function SourceRequired({ type }: { type: 'flashcards' | 'quiz' }) {
  const label = type === 'flashcards' ? 'Flashcards' : 'Quizzes'

  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] text-center px-6 max-w-lg mx-auto">
      <FileText className="size-20 text-slate-300 mb-6" />
      <h1 className="font-display text-3xl font-semibold text-slate-900 mb-3">
        {label} need a source
      </h1>
      <p className="text-lg text-slate-500 leading-relaxed mb-8">
        Select a document in Notebooks and generate {label.toLowerCase()} from that source.
        You cannot create them manually.
      </p>
      <Button asChild size="lg" className="bg-mode-library hover:bg-mode-library-hover text-lg h-12 px-8">
        <Link href="/dashboard/notebooks">
          <BookMarked className="size-5 mr-2" />
          Go to Notebooks
        </Link>
      </Button>
    </div>
  )
}
