'use client'

import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import useSWR from 'swr'
import { analyticsAPI } from '@/lib/api'
import {
  BarChart3,
  BookMarked,
  Brain,
  Clock,
  FileText,
  Loader2,
  Map,
  Route,
  Sparkles,
  Target,
  TrendingUp,
  Zap,
} from 'lucide-react'

type Summary = {
  notebooks_count: number
  sources_count: number
  flashcards_count: number
  quizzes_count: number
  quiz_attempts_count: number
  quiz_attempts_completed: number
  average_quiz_score: number | null
  total_study_minutes: number
  study_sessions_count: number
  flashcard_reviews: number
  flashcard_accuracy: number | null
}

type Recommendation = {
  subject: string
  topic: string
  subtopic: string
  label: string
  priority: number
  recommended_difficulty: string
  reason: string
}

type PathStep = {
  step: number
  subject: string
  topic: string
  subtopic: string
  difficulty: string
  status: string
}

export default function AnalyticsPage() {
  const { data: summaryRes, mutate: refreshSummary } = useSWR(['/analytics/summary'], () =>
    analyticsAPI.getSummary()
  )
  const { data: sessionsRes, mutate: refreshSessions } = useSWR(['/analytics/sessions'], () =>
    analyticsAPI.getStudySessions()
  )
  const { data: subjectsRes } = useSWR(['/analytics/subjects'], () => analyticsAPI.getSubjects())

  const [studyContext, setStudyContext] = useState('')
  const [pathSubject, setPathSubject] = useState('')

  const { data: recsRes, isLoading: recsLoading } = useSWR(
    ['/analytics/recommendations', studyContext],
    () => analyticsAPI.getRecommendations({ text: studyContext, limit: 5 })
  )
  const { data: pathRes, isLoading: pathLoading } = useSWR(
    ['/analytics/learning-path', pathSubject],
    () => analyticsAPI.getLearningPath({ subject: pathSubject || undefined, limit: 12 })
  )

  const summary: Summary | null = summaryRes?.data ?? null
  const sessions = sessionsRes?.data?.results ?? sessionsRes?.data ?? []
  const recommendations: Recommendation[] = recsRes?.data?.recommendations ?? []
  const learningPath: PathStep[] = pathRes?.data?.learning_path ?? []
  const subjects: string[] = subjectsRes?.data?.subjects ?? []

  const [logging, setLogging] = useState(false)
  const [minutes, setMinutes] = useState('30')
  const [topic, setTopic] = useState('')
  const [moodBefore, setMoodBefore] = useState('good')
  const [moodAfter, setMoodAfter] = useState('good')

  const handleLogSession = async (e: React.FormEvent) => {
    e.preventDefault()
    setLogging(true)
    try {
      await analyticsAPI.createStudySession({
        duration_minutes: Math.max(1, parseInt(minutes, 10) || 1),
        material_studied: topic || 'Manual study session',
        mood_before: moodBefore,
        mood_after: moodAfter,
      })
      setTopic('')
      refreshSummary()
      refreshSessions()
    } finally {
      setLogging(false)
    }
  }

  if (!summary) {
    return (
      <div className="flex justify-center py-24">
        <Loader2 className="size-10 animate-spin text-mode-analytics" />
      </div>
    )
  }

  const stats = [
    {
      label: 'Notebooks',
      value: summary.notebooks_count,
      icon: BookMarked,
      color: 'text-mode-library',
    },
    {
      label: 'Sources',
      value: summary.sources_count,
      icon: FileText,
      color: 'text-sky-500',
    },
    {
      label: 'Flashcards',
      value: summary.flashcards_count,
      icon: Zap,
      color: 'text-mode-flashcards',
    },
    {
      label: 'Quizzes taken',
      value: summary.quiz_attempts_completed,
      icon: Target,
      color: 'text-mode-quizzes',
    },
    {
      label: 'Avg quiz score',
      value: summary.average_quiz_score != null ? `${summary.average_quiz_score}%` : '—',
      icon: TrendingUp,
      color: 'text-mode-analytics',
    },
    {
      label: 'Study time logged',
      value: `${summary.total_study_minutes}m`,
      icon: Clock,
      color: 'text-mode-library',
    },
  ]

  const difficultyColor = (d: string) => {
    if (d === 'easy') return 'text-emerald-700 bg-emerald-50'
    if (d === 'hard') return 'text-rose-700 bg-rose-50'
    return 'text-amber-700 bg-amber-50'
  }

  const statusColor = (s: string) => {
    if (s === 'current') return 'border-emerald-300 bg-emerald-50'
    if (s === 'next') return 'border-blue-300 bg-blue-50'
    return 'border-slate-200 bg-slate-50'
  }

  return (
    <div className="space-y-8 max-w-5xl">
      <div className="rise border-t-[3px] border-mode-analytics pt-4">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-analytics">
          Analytics
        </p>
        <h1 className="font-display text-3xl md:text-4xl font-semibold text-slate-900 mt-1 flex items-center gap-3 text-balance">
          <BarChart3 className="size-8 text-mode-analytics shrink-0" />
          Your progress
        </h1>
        <p className="text-lg text-slate-500 mt-2 text-pretty">
          Study activity, AI recommendations, and a personalized learning path.
        </p>
      </div>

      {/* Summary strip: one panel, hairline-divided cells (1px gap over a
          slate backing) — an instrument readout rather than floating tiles. */}
      <dl className="rise grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-100 shadow-sheet" style={{ animationDelay: '60ms' }}>
        {stats.map((stat) => {
          const Icon = stat.icon
          return (
            <div key={stat.label} className="bg-white p-5">
              <dt className="flex items-center gap-2 text-slate-500 text-sm">
                <Icon className={`size-4 ${stat.color} shrink-0`} />
                <span className="truncate">{stat.label}</span>
              </dt>
              <dd className="font-mono text-3xl font-semibold text-slate-900 tabular-nums mt-2">
                {stat.value}
              </dd>
            </div>
          )
        })}
      </dl>

      {/* ML Insights */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="border-slate-200 shadow-sheet p-6">
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="size-5 text-mode-quizzes" />
            <h2 className="text-xl font-semibold text-slate-900">Study Recommendations</h2>
          </div>
          <p className="text-sm text-slate-500 mb-4">
            Content-based suggestions from your performance and study material (TF-IDF + topic hierarchy).
          </p>
          <div className="space-y-2 mb-4">
            <Label htmlFor="study-context">Optional study context</Label>
            <Input
              id="study-context"
              value={studyContext}
              onChange={(e) => setStudyContext(e.target.value)}
              placeholder="e.g. photosynthesis chloroplast biology"
            />
          </div>
          {recsLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="size-6 animate-spin text-mode-quizzes" />
            </div>
          ) : recommendations.length > 0 ? (
            <div className="space-y-3">
              {recommendations.map((rec, i) => (
                <div
                  key={`${rec.label}-${i}`}
                  className="p-4 rounded-lg border border-slate-200 bg-slate-50"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-slate-900 font-medium">{rec.subtopic}</p>
                      <p className="text-slate-500 text-sm">{rec.topic} · {rec.subject}</p>
                    </div>
                    <span className={`text-xs px-2 py-1 rounded-full shrink-0 ${difficultyColor(rec.recommended_difficulty)}`}>
                      {rec.recommended_difficulty}
                    </span>
                  </div>
                  <p className="text-slate-500 text-sm mt-2">{rec.reason}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500 text-sm py-4">
              No recommendations yet. Upload notes or complete quizzes to personalize suggestions.
            </p>
          )}
        </Card>

        <Card className="border-slate-200 shadow-sheet p-6">
          <div className="flex items-center gap-2 mb-4">
            <Route className="size-5 text-mode-library" />
            <h2 className="text-xl font-semibold text-slate-900">Adaptive Learning Path</h2>
          </div>
          <p className="text-sm text-slate-500 mb-4">
            Topics ordered by difficulty and Bloom level — skips areas you&apos;ve mastered.
          </p>
          <div className="space-y-2 mb-4">
            <Label htmlFor="path-subject">Filter by subject</Label>
            <select
              id="path-subject"
              value={pathSubject}
              onChange={(e) => setPathSubject(e.target.value)}
              className="w-full h-10 rounded-md border border-slate-300 bg-white px-3 text-slate-900 text-base"
            >
              <option value="">All subjects</option>
              {subjects.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          {pathLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="size-6 animate-spin text-mode-library" />
            </div>
          ) : learningPath.length > 0 ? (
            <div className="space-y-2">
              {learningPath.map((step) => (
                <div
                  key={`${step.step}-${step.subtopic}`}
                  className={`p-3 rounded-lg border flex items-center gap-3 ${statusColor(step.status)}`}
                >
                  <span className="font-mono flex items-center justify-center size-8 rounded-full bg-white border border-slate-200 text-slate-600 text-sm font-semibold shrink-0">
                    {step.step}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-slate-900 font-medium truncate">{step.subtopic}</p>
                    <p className="text-slate-500 text-xs">{step.topic} · {step.subject}</p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${difficultyColor(step.difficulty)}`}>
                    {step.difficulty}
                  </span>
                  {step.status === 'current' && (
                    <Map className="size-4 text-mode-analytics shrink-0" />
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500 text-sm py-4">Learning path unavailable. Ensure ML models are trained.</p>
          )}
        </Card>
      </div>

      <Card className="border-slate-200 shadow-sheet p-5">
        <div className="flex items-start gap-3">
          <span className="rounded-lg bg-mode-quizzes/10 p-2 shrink-0">
            <Brain className="size-5 text-mode-quizzes" />
          </span>
          <div>
            <p className="text-slate-900 font-medium">Powered by a local ML pipeline</p>
            <p className="text-slate-500 text-sm mt-1 leading-relaxed max-w-2xl">
              Flashcards use spaCy NER, quizzes use TF-IDF distractors, and recommendations use
              scikit-learn content-based filtering. Set{' '}
              <code className="font-mono text-mode-quizzes bg-mode-quizzes/10 px-1.5 py-0.5 rounded">
                USE_ML_PRIMARY=True
              </code>{' '}
              in backend/.env for fully offline generation.
            </p>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="border-slate-200 shadow-sheet p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">Log a study session</h2>
          <form onSubmit={handleLogSession} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="minutes">Minutes</Label>
                <Input
                  id="minutes"
                  type="number"
                  min={1}
                  value={minutes}
                  onChange={(e) => setMinutes(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="topic">Topic</Label>
                <Input
                  id="topic"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="e.g. Biology revision"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="mood-before">Mood before</Label>
                <select
                  id="mood-before"
                  value={moodBefore}
                  onChange={(e) => setMoodBefore(e.target.value)}
                  className="w-full h-10 rounded-md border border-slate-300 bg-white px-3 text-slate-900 text-base"
                >
                  <option value="great">Great</option>
                  <option value="good">Good</option>
                  <option value="neutral">Neutral</option>
                  <option value="tired">Tired</option>
                  <option value="unmotivated">Unmotivated</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="mood-after">Mood after</Label>
                <select
                  id="mood-after"
                  value={moodAfter}
                  onChange={(e) => setMoodAfter(e.target.value)}
                  className="w-full h-10 rounded-md border border-slate-300 bg-white px-3 text-slate-900 text-base"
                >
                  <option value="great">Great</option>
                  <option value="good">Good</option>
                  <option value="neutral">Neutral</option>
                  <option value="tired">Tired</option>
                  <option value="unmotivated">Unmotivated</option>
                </select>
              </div>
            </div>
            <Button type="submit" disabled={logging} className="w-full h-11">
              {logging ? <Loader2 className="size-4 animate-spin" /> : 'Save session'}
            </Button>
          </form>
          <p className="text-sm text-slate-500 mt-4">
            Completing a quiz also logs time automatically.
          </p>
        </Card>

        <Card className="border-slate-200 shadow-sheet p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">Flashcard reviews</h2>
          <p className="font-mono text-4xl font-semibold text-slate-900 tabular-nums">
            {summary.flashcard_reviews}
          </p>
          <p className="text-slate-500 mt-2">Total correct + incorrect review counts</p>
          {summary.flashcard_accuracy != null && (
            <p className="text-lg text-mode-analytics mt-4">
              Accuracy when reviewed: {summary.flashcard_accuracy}%
            </p>
          )}
          {summary.flashcard_reviews === 0 && (
            <p className="text-sm text-slate-500 mt-4">
              Review counts update when flashcard practice tracking is used.
            </p>
          )}
        </Card>
      </div>

      <Card className="border-slate-200 p-6">
        <h2 className="text-xl font-semibold text-slate-900 mb-4">Recent study sessions</h2>
        <div className="space-y-3">
          {sessions.slice(0, 8).map((session: {
            id: number
            material_studied?: string
            duration_minutes: number
            started_at: string
            mood_before?: string
            mood_after?: string
            notes?: string
          }) => (
            <div
              key={session.id}
              className="p-4 bg-slate-50 rounded-lg border border-slate-200 flex justify-between gap-4"
            >
              <div className="min-w-0">
                <p className="text-slate-900 font-medium truncate">
                  {session.material_studied || 'Study session'}
                </p>
                <p className="text-slate-500 text-sm mt-1">
                  {new Date(session.started_at).toLocaleString()}
                  {session.notes ? ` · ${session.notes}` : ''}
                </p>
              </div>
              <span className="font-mono text-slate-600 font-semibold shrink-0">
                {session.duration_minutes}m
              </span>
            </div>
          ))}
          {sessions.length === 0 && (
            <p className="text-slate-500">
              No sessions yet. Log one above or finish a quiz to record activity.
            </p>
          )}
        </div>
      </Card>
    </div>
  )
}
