'use client'

import { Suspense, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { useTranslations } from 'next-intl'
import { ArrowRight, ChevronLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { PageHeader } from '@/components/page-header'
import { InPageLanguage, useInPageLanguage } from '@/components/in-page-language'
import { mockTestsAPI, type RedoQuestion, type RedoVerdict } from '@/lib/api'
import { isShort } from '@/lib/translate'

/** A notebook's missed questions, redone like a quiz: one at a time, marked
 *  as soon as it is answered, no clock. Each answer counts toward the
 *  mistake bank's rule (two right in a row and the question leaves it). */
function MistakeRedo() {
  const t = useTranslations('quizzes')
  const notebook = Number(useSearchParams().get('notebook'))
  const { data, isLoading, error, mutate } = useSWR(
    Number.isInteger(notebook) && notebook > 0 ? ['/quizzes/mistakes/redo', notebook] : null,
    () => mockTestsAPI.redoMistakes(notebook),
    { revalidateOnFocus: false }      // a refetch mid-round would reshuffle what is left
  )
  const questions: RedoQuestion[] = data?.data?.questions ?? []

  const [index, setIndex] = useState(0)
  const [picked, setPicked] = useState<string | null>(null)
  const [verdict, setVerdict] = useState<RedoVerdict | null>(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const [tally, setTally] = useState({ right: 0, cleared: 0 })
  const [done, setDone] = useState(false)
  const found = useInPageLanguage([...questions.flatMap((q) => [q.question_text, ...q.options]), verdict?.explanation])

  const back = (
    <Button asChild variant="outline">
      <Link href="/dashboard/analytics"><ChevronLeft aria-hidden />{t('redoBack')}</Link>
    </Button>
  )
  const header = <PageHeader title={t('redoTitle')} meta={data?.data?.notebook?.title} action={back} />

  if (isLoading) {
    return <div className="mx-auto max-w-3xl space-y-8">{header}<div className="sheet h-72 animate-pulse" aria-busy /></div>
  }
  if (error || questions.length === 0) {
    return (
      <div className="mx-auto max-w-3xl space-y-8">
        {header}
        <p className="sheet p-8 text-lg text-slate-700">{error ? t('redoFailed') : t('redoEmpty')}</p>
      </div>
    )
  }

  if (done) {
    return (
      <div className="mx-auto max-w-3xl space-y-8">
        {header}
        <div className="sheet space-y-5 p-8">
          <p className="text-lg text-slate-800">
            {t('redoDone', { right: tally.right, total: questions.length, cleared: tally.cleared })}
          </p>
          {tally.cleared < questions.length && (
            <Button
              type="button"
              onClick={() => {
                setIndex(0)
                setPicked(null)
                setVerdict(null)
                setTally({ right: 0, cleared: 0 })
                setDone(false)
                void mutate()
              }}
            >
              {t('redoAgain')}
            </Button>
          )}
        </div>
      </div>
    )
  }

  const question = questions[index]
  const last = index >= questions.length - 1

  const check = async () => {
    if (!picked || busy) return
    setBusy(true)
    setFailed(false)
    try {
      const res = await mockTestsAPI.redoAnswer(notebook, question.id, picked)
      setVerdict(res.data)
      setTally((s) => ({ right: s.right + (res.data.is_correct ? 1 : 0), cleared: s.cleared + (res.data.cleared ? 1 : 0) }))
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  const next = () => {
    if (last) {
      setDone(true)
      return
    }
    setIndex((i) => i + 1)
    setPicked(null)
    setVerdict(null)
  }

  const label = (opt: string) =>
    opt === 'True' ? t('true') : opt === 'False' ? t('false') : (
      <InPageLanguage text={opt} found={found} context={isShort(opt) ? question.question_text : undefined} />
    )

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      {header}
      <p className="-mt-4 font-mono text-sm tabular-nums text-slate-600">
        {t('questionOf', { n: index + 1, total: questions.length })}
      </p>

      <Card className="relative p-8 md:p-10">
        <span className="absolute left-8 -top-px h-[3px] w-12 rounded-b-full bg-mode md:left-10" aria-hidden />
        <p className="mb-8 text-2xl leading-relaxed text-slate-900 md:text-[1.75rem] text-pretty">
          <InPageLanguage text={question.question_text} found={found} />
        </p>
        <div className="space-y-3">
          {question.options.map((opt) => {
            let style = 'border-slate-200 bg-white hover:bg-slate-50'
            if (verdict) {
              if (opt === verdict.correct_answer) style = 'border-emerald-400 bg-emerald-50 text-emerald-950'
              else if (opt === picked) style = 'border-red-300 bg-red-50 text-red-950'
            } else if (picked === opt) {
              style = 'border-mode bg-mode/10'
            }
            return (
              <button
                key={opt}
                type="button"
                disabled={verdict !== null}
                onClick={() => setPicked(opt)}
                className={`w-full rounded-lg border px-4 py-3 text-left text-lg text-slate-900 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30 ${style}`}
              >
                {label(opt)}
              </button>
            )
          })}
        </div>
        {verdict && (
          <div className="mt-6 space-y-2">
            {verdict.is_correct && (
              <p className={verdict.cleared ? 'text-base font-medium text-emerald-700' : 'text-base text-slate-700'}>
                {verdict.cleared ? t('redoCleared') : t('redoStays')}
              </p>
            )}
            {verdict.explanation && (
              <p className="text-lg leading-relaxed text-slate-500">
                <InPageLanguage text={verdict.explanation} found={found} />
              </p>
            )}
          </div>
        )}
        {failed && <p role="alert" className="mt-4 text-base text-red-700">{t('redoFailed')}</p>}
      </Card>

      <div className="flex justify-center">
        {verdict ? (
          <Button size="lg" onClick={next} className="px-8">
            {last ? t('finish') : t('nextQuestion')}
            <ArrowRight aria-hidden />
          </Button>
        ) : (
          <Button size="lg" disabled={!picked || busy} onClick={() => void check()} className="px-8">
            {t('checkAnswer')}
          </Button>
        )}
      </div>
    </div>
  )
}

export default function MistakeRedoPage() {
  return (
    <Suspense fallback={null}>
      <MistakeRedo />
    </Suspense>
  )
}
