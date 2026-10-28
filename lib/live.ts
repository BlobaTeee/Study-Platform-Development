// A live round as the browser holds it, and the little arithmetic around it.
// The server owns the round; these only keep a tab's copy in step.

export type LiveStatus = 'lobby' | 'question' | 'reveal' | 'finished'

export type LivePlayer = { user_id: number; name: string; score: number; answered: boolean }

export type LiveResult = { user_id: number; name: string; score: number; ms: number; rank: number }

export type LiveMiss = { question_id: number; text: string; your_answer: string; correct: string; explanation: string }

export type LiveState = {
  id: number
  notebook: { id: number; title: string }
  host: { user_id: number; name: string }
  status: LiveStatus
  index: number
  total: number
  seconds: number
  players: LivePlayer[]
  question: { id: number; text: string; type: string; options: string[] } | null
  remaining_ms: number
  answered_count: number
  reveal: {
    correct: string
    counts: Record<string, number>
    right: number[]
    explanation: string
    source_title: string
    source_excerpt: string
  } | null
  next_open_ms: number
  results: LiveResult[]
  you: { user_id: number; is_host: boolean; joined: boolean; answer: string | null; missed: LiveMiss[] }
}

/** What the socket broadcasts: the room without anyone's own seat. */
export type LiveBroadcast = Omit<LiveState, 'you'>

export type LiveRoomSummary = {
  id: number
  status: LiveStatus
  notebook: { id: number; title: string }
  host: { user_id: number; name: string }
  players: number
  /** Whether I am in it; only in the list I fetch, not in a broadcast. */
  joined?: boolean
}

/** Whole seconds left on a countdown, rounded up, never negative. */
export function secondsLeft(deadlineAt: number, now: number): number {
  return Math.max(0, Math.ceil((deadlineAt - now) / 1000))
}

/** How the room split over the options, in the options' own order. */
export function optionShares(counts: Record<string, number>, options: string[]) {
  const total = options.reduce((sum, o) => sum + (counts[o] ?? 0), 0)
  return options.map((option) => {
    const n = counts[option] ?? 0
    return { option, n, share: total ? n / total : 0 }
  })
}

/** A broadcast applied to this tab's copy: the shared part replaced, my own
 *  seat kept, and my answer dropped once the room is on another question. */
export function applyBroadcast(prev: LiveState, next: LiveBroadcast): LiveState {
  const sameQuestion = next.index === prev.index && next.status !== 'lobby'
  return {
    ...next,
    you: {
      ...prev.you,
      is_host: next.host.user_id === prev.you.user_id,
      answer: sameQuestion ? prev.you.answer : null,
    },
  }
}
