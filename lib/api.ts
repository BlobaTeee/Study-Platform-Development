import axios from 'axios'
import type { LiveRoomSummary, LiveState } from './live'
import type { BuildLink, BuildResult } from './map-build'
import { readLocaleCookie } from '@/i18n/locale'
import { supabase } from './supabase-client'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Attach the current Supabase access token to every request
api.interceptors.request.use(
  async (config) => {
    const token = supabase ? (await supabase.auth.getSession()).data.session?.access_token : undefined
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    // The API translates its own messages (Django LocaleMiddleware); tell it
    // which language this browser is showing.
    const lang = readLocaleCookie()
    if (lang) {
      config.headers['Accept-Language'] = lang
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Handle response errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export const authAPI = {
  getProfile: () => api.get('/users/profiles/me/'),
  updateProfile: (data: any) => api.put('/users/profiles/update_profile/', data),
  // Everything of theirs, here and at Supabase. 503 means try again.
  deleteAccount: () => api.delete('/users/profiles/me/'),
}

/** How well you recalled a card, worst first. Drives the SM-2 schedule. */
export type ReviewGrade = 'hard' | 'good' | 'easy'

export type TutorTurn = { role: 'user' | 'tutor'; text: string }

export const flashcardsAPI = {
  getFlashcards: (params?: any) => api.get('/flashcards/flashcards/', { params }),
  createFlashcard: (data: any) => api.post('/flashcards/flashcards/', data),
  updateFlashcard: (id: number, data: any) => api.put(`/flashcards/flashcards/${id}/`, data),
  // A question about a card whose answer is showing; three per card per session.
  askTutor: (id: number, data: { question: string; history: TutorTurn[] }) =>
    api.post<{ answer: string }>(`/flashcards/flashcards/${id}/ask/`, data),
  deleteFlashcard: (id: number) => api.delete(`/flashcards/flashcards/${id}/`),
  // Self-graded review: the backend schedules the card's next appearance and
  // this is what analytics counts. No study session needed.
  recordReview: (flashcardId: number, result: ReviewGrade) =>
    api.post('/study/card-reviews/record/', { flashcard_id: flashcardId, result }),
  // Cards the SM-2 schedule says are owed today, plus ones never studied.
  // Cards scheduled ahead are deliberately withheld.
  // With `sourceIds`, the server picks today's share from those documents only;
  // filtering a global share afterwards could leave a document looking caught up.
  getDueCards: (sourceIds: number[] = []) =>
    api.get('/study/card-reviews/due_today/', {
      params: sourceIds.length ? { source: sourceIds.join(',') } : undefined,
    }),
}

export const streaksAPI = {
  // Current/best consecutive-day streak. Advances when a card is reviewed.
  getMe: () => api.get('/study/streaks/me/'),
}

export type ForgottenGroup = {
  key: string
  label: string
  card_ids: number[]
  count: number
  sample: string
}

/** One notebook's forgotten cards, grouped by concept within it. */
export type ForgottenNotebook = {
  notebook_id: number | null
  title: string
  count: number
  card_ids: number[]
  groups: ForgottenGroup[]
}

/** A mix-up the student keeps making, named from their wrong answers. */
export type Misconception = { key: string; confused: string; with: string; difference: string; evidence: number; examples: string[] }
export type MisconceptionNotebook = { notebook_id: number; title: string; items: Misconception[] }

/** One notebook's memory forecast: expected numbers of studied cards. */
export type NotebookForecast = {
  notebook_id: number; title: string; has_exam: boolean; days_ahead: number
  studied: number; unseen: number; now: number; at_exam: number
  suggestion: { card_ids: number[]; at_exam: number }
}

export const reviewsAPI = {
  // Reviews done and recall accuracy over the last 7 days — a real week window,
  // unlike the all-time counts on the analytics summary.
  getWeeklyStats: () => api.get('/study/card-reviews/stats/'),
  getForecast: () => api.get<{ notebooks: NotebookForecast[] }>('/study/forecast/'),
  getMisconceptions: () => api.get<{ notebooks: MisconceptionNotebook[]; pending: boolean }>('/quizzes/misconceptions/'),
  // Makes that mix-up's contrast cards (once) and returns their ids to study.
  practiseMisconception: (notebookId: number, key: string) =>
    api.post<{ card_ids: number[] }>('/quizzes/misconceptions/practice/', { notebook_id: notebookId, key }),
  // Cards last answered wrong, grouped by concept, so they can be relearned
  // one idea at a time.
  getForgottenGroups: () => api.get<{ notebooks: ForgottenNotebook[] }>('/study/card-reviews/forgotten_groups/'),
}

export type FeynmanFeedback = {
  id: number
  concept: string
  text: string
  correct: string[]
  missing: string[]
  wrong: { claim: string; correction: string }[]
  level: 'solid' | 'most' | 'reread'
  reread: { source_id: number; notebook_id: number; title: string; passage: string }[]
}

// Explain a concept in your own words; feedback is judged against the
// passages the cards came from. GET returns the last attempt ({} if none).
export const explainAPI = {
  latest: (cardIds: number[]) =>
    api.get<FeynmanFeedback | Record<string, never>>('/study/explain/', { params: { cards: cardIds.join(',') } }),
  submit: (data: { card_ids: number[]; concept: string; text: string }) =>
    api.post<FeynmanFeedback>('/study/explain/', data),
}

// Practice problems: apply a document to a case it does not spell out, solve
// in steps, graded against a rubric the page never sees until solved.
export type ErrorType = 'misread' | 'concept' | 'missing_step' | 'execution' | 'unsupported'
export type ExerciseSummary = {
  id: number; notebook_id: number | null; source_id: number | null; origin: 'document' | 'own'
  prompt: string; difficulty: 'easy' | 'medium' | 'hard'; notebook_title: string; source_title: string
  status: 'new' | 'mastered' | 'revisit'; revisit_on: string | null; due: boolean; attempted: boolean; created_at: string
}
export type ExerciseResult = {
  verdict?: 'passed' | 'needs_work'; met?: number[]; first_wrong_step?: number | null
  error_type?: ErrorType | null; detail?: string; hint?: string
}
export type ExerciseDetail = ExerciseSummary & {
  attempts: { id: number; kind: 'submit' | 'hint' | 'reveal'; steps: string[]; result: ExerciseResult; created_at: string }[]
  checkpoint_count: number
  met_checkpoints: { id: number; text: string; basis: string }[]
  failed_submits: number; can_reveal: boolean
  solution: string[] | null; mistakes: { text: string; type: ErrorType }[] | null
}
export type PracticeMistakes = {
  notebook_id: number | null; title: string; total: number
  types: { type: ErrorType; count: number; exercise_ids: number[] }[]
}

/** One question read from a photo; the instruction is its section's (how to answer). */
export type PhotoQuestion = { label: string; instruction: string; text: string }

export const exercisesAPI = {
  list: (params: { notebook?: number; source?: number; own?: 1 }) =>
    api.get<{ results: ExerciseSummary[] }>('/exercises/', { params }),
  generate: (sourceId: number) =>
    api.post<{ results: ExerciseSummary[] }>('/exercises/generate/', { source_id: sourceId }),
  // The student's own problem: in no notebook, graded from general knowledge.
  own: (text: string) => api.post<ExerciseDetail>('/exercises/own/', { text }),
  // A photo read into its questions (maths in LaTeX), for the student to pick
  // one; the photo is not kept.
  readPhoto: (file: File) => {
    const form = new FormData()
    form.append('image', file)
    return api.post<{ questions: PhotoQuestion[] }>('/exercises/read-photo/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  get: (id: number) => api.get<ExerciseDetail>(`/exercises/${id}/`),
  remove: (id: number) => api.delete(`/exercises/${id}/`),
  submit: (id: number, steps: string[]) => api.post<ExerciseDetail>(`/exercises/${id}/submit/`, { steps }),
  hint: (id: number, steps: string[]) => api.post<ExerciseDetail>(`/exercises/${id}/hint/`, { steps }),
  reveal: (id: number) => api.post<ExerciseDetail>(`/exercises/${id}/reveal/`),
  mistakes: () => api.get<{ notebooks: PracticeMistakes[] }>('/exercises/mistakes/'),
}

// Live rounds in a shared notebook. Every step is a call; the room hears of
// it over the socket (live:state), and a reconnecting tab just fetches.
export const liveAPI = {
  open: () => api.get<{ rooms: LiveRoomSummary[] }>('/live/rooms/'),
  create: (notebook: number, options: { question_count?: number; seconds?: number } = {}) =>
    api.post<LiveState>('/live/rooms/', { notebook, ...options }),
  get: (id: number) => api.get<LiveState>(`/live/rooms/${id}/`),
  join: (id: number) => api.post<LiveState>(`/live/rooms/${id}/join/`),
  start: (id: number) => api.post<LiveState>(`/live/rooms/${id}/start/`),
  answer: (id: number, index: number, choice: string) =>
    api.post<LiveState>(`/live/rooms/${id}/answer/`, { index, choice }),
  reveal: (id: number) => api.post<LiveState>(`/live/rooms/${id}/reveal/`),
  next: (id: number, index: number) => api.post<LiveState>(`/live/rooms/${id}/next/`, { index }),
  leave: (id: number) => api.post<LiveState>(`/live/rooms/${id}/leave/`),
}

export const quizzesAPI = {
  getQuizzes: (params?: any) => api.get('/quizzes/quizzes/', { params }),
  getAttempts: () => api.get('/quizzes/attempts/'),
  createQuiz: (data: any) => api.post('/quizzes/quizzes/', data),
  // Fixing a generated question. The server rejects a correct_answer that is
  // not one of the options, and a quiz that is not the caller's.
  updateQuestion: (id: number, data: { question_text?: string; options?: string[]; correct_answer?: string; explanation?: string }) =>
    api.patch(`/quizzes/questions/${id}/`, data),
  deleteQuestion: (id: number) => api.delete(`/quizzes/questions/${id}/`),
  startAttempt: (quizId: number) => api.post(`/quizzes/quizzes/${quizId}/start_attempt/`, {}),
  submitAnswer: (attemptId: number, data: any) => api.post(`/quizzes/attempts/${attemptId}/submit_answer/`, data),
  completeQuiz: (attemptId: number, data: any) => api.post(`/quizzes/attempts/${attemptId}/complete/`, data),
  gradeTypedAnswer: (attemptId: number, data: { question_id: number; answer: string }) =>
    api.post(`/quizzes/attempts/${attemptId}/grade_typed_answer/`, data),
  overrideAnswer: (attemptId: number, data: { answer_id: number; is_correct: boolean }) =>
    api.post(`/quizzes/attempts/${attemptId}/override_answer/`, data),
}

export type ChatMessage = {
  id: number
  group: number
  body: string
  created_at: string
  author: { user_id: number; name: string; is_you?: boolean }
}

export type ChatLastLine = {
  id: number
  body: string
  created_at: string
  is_you: boolean
  author: string
}

export type ChatOverview = {
  groups: { id: number; name: string; members: number; last: ChatLastLine | null }[]
  people: { user_id: number; name: string; last: ChatLastLine | null }[]
}

export type DirectMessageRow = {
  id: number
  with: number
  body: string
  created_at: string
  author: { user_id: number; name: string; is_you?: boolean }
}

export type NotebookMemberRow = {
  user_id: number
  name: string
  email: string
  role: 'owner' | 'member'
  is_you: boolean
  reviews: number
  accuracy: number | null
}

/** A document's main idea, with the passage it was read from. */
export type KeyPoint = { point: string; label?: string; importance: 'core' | 'supporting'; passage: string }

export type AutoUploadResult = {
  source: { id: number; title: string }
  notebook: { id: number; title: string }
  created_notebook: boolean
}

export const notebooksAPI = {
  getNotebooks: () => api.get('/notebooks/notebooks/'),
  getNotebook: (id: number) => api.get(`/notebooks/notebooks/${id}/`),
  createNotebook: (data: { title: string; description?: string }) =>
    api.post('/notebooks/notebooks/', data),
  // A CSV of the notebook's live cards or published questions. Fetched with
  // the auth header (a plain <a href> could not carry it) and saved client-side.
  exportCsv: (id: number, kind: 'flashcards' | 'questions') =>
    api.get<Blob>(`/notebooks/notebooks/${id}/export/`, { params: { kind }, responseType: 'blob' }),
  // Chat groups. Sending goes over REST so a message is never lost to a
  // dropped socket; the socket is how everyone else hears it.
  createGroup: (data: { name: string; members: number[] }) =>
    api.post<{ id: number; name: string }>('/notebooks/chat/groups/', data),
  groupMessages: (groupId: number, params?: { before?: number }) =>
    api.get<{ messages: ChatMessage[] }>(`/notebooks/chat/groups/${groupId}/messages/`, { params }),
  sendGroupMessage: (groupId: number, body: string) =>
    api.post<ChatMessage>(`/notebooks/chat/groups/${groupId}/messages/`, { body }),
  addGroupMember: (groupId: number, userId: number) =>
    api.post(`/notebooks/chat/groups/${groupId}/members/`, { user_id: userId }),
  leaveGroup: (groupId: number, userId: number) =>
    api.delete(`/notebooks/chat/groups/${groupId}/members/${userId}/`),
  deleteMessage: (messageId: number) => api.delete(`/notebooks/messages/${messageId}/`),
  // What the chat launcher lists, and the private threads inside it.
  chatOverview: () => api.get<ChatOverview>('/notebooks/chat/overview/'),
  directThread: (userId: number, params?: { before?: number }) =>
    api.get<{ messages: DirectMessageRow[] }>(`/notebooks/chat/direct/${userId}/`, { params }),
  sendDirect: (userId: number, body: string) =>
    api.post<DirectMessageRow>(`/notebooks/chat/direct/${userId}/`, { body }),
  // Sharing: who is in a notebook, inviting, leaving, removing.
  members: (id: number) =>
    api.get<{ members: NotebookMemberRow[] }>(`/notebooks/notebooks/${id}/members/`),
  invite: (id: number, email: string) =>
    api.post<{ email: string; url: string; emailed: boolean }>(`/notebooks/notebooks/${id}/invite/`, { email }),
  removeMember: (id: number, userId: number) =>
    api.delete(`/notebooks/notebooks/${id}/members/${userId}/`),
  acceptInvite: (token: string) =>
    api.post<{ notebook: { id: number; title: string } }>('/notebooks/invites/accept/', { token }),
  updateNotebook: (id: number, data: { title?: string; description?: string }) =>
    api.patch(`/notebooks/notebooks/${id}/`, data),
  deleteNotebook: (id: number) => api.delete(`/notebooks/notebooks/${id}/`),
  getSource: (id: number) => api.get(`/notebooks/sources/${id}/`),
  /** A document's texts in the page language; the originals when the model is not available. */
  // `contexts[i]`: the question texts[i] answers, for a short answer; null otherwise.
  translate: (texts: string[], to: string, contexts?: (string | null)[]) =>
    api.post<{ translations: string[]; translated: boolean }>('/notebooks/translate/', { texts, to, contexts }),
  // Read an older document's main ideas now; kept once read.
  readSource: (id: number) => api.post(`/notebooks/sources/${id}/read/`),
  deleteSource: (id: number) => api.delete(`/notebooks/sources/${id}/`),
  uploadSource: (notebookId: number, file: File, title?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (title) form.append('title', title)
    return api.post(`/notebooks/notebooks/${notebookId}/upload_pdf/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  // From the notebooks page: the server places the file in the notebook for
  // its subject, making one if needed.
  autoUpload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<AutoUploadResult>('/notebooks/notebooks/auto_upload/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  moveSource: (sourceId: number, to: { notebook_id?: number; new_notebook_title?: string; drop_empty_notebook?: boolean }) =>
    api.post<{ notebook: { id: number; title: string } }>(`/notebooks/sources/${sourceId}/move/`, to),
  uploadPdf: (notebookId: number, file: File, title?: string) =>
    notebooksAPI.uploadSource(notebookId, file, title),
  addTextSource: (notebookId: number, data: { text: string; title?: string }) =>
    api.post(`/notebooks/notebooks/${notebookId}/add_text/`, data),
  addUrlSource: (notebookId: number, data: { url: string; title?: string }) =>
    api.post(`/notebooks/notebooks/${notebookId}/add_url/`, data),
  // How many flashcards this exact source selection already holds. Generating
  // replaces that deck, so the page needs this to say what a press retires.
  getMaterialCounts: (notebookId: number, sourceIds: number[]) =>
    api.get(`/notebooks/notebooks/${notebookId}/material_counts/`, {
      params: { source_ids: sourceIds.join(',') },
    }),
  generateFlashcardsFromSources: (
    notebookId: number,
    sourceIds: number[],
    count = 10
  ) =>
    api.post(`/notebooks/notebooks/${notebookId}/generate_flashcards/`, {
      source_ids: sourceIds,
      count,
    }),
  generateQuizFromSources: (
    notebookId: number,
    sourceIds: number[],
    questionCount = 8
  ) =>
    api.post(`/notebooks/notebooks/${notebookId}/generate_quiz/`, {
      source_ids: sourceIds,
      question_count: questionCount,
    }),
  generateFlashcards: (sourceId: number, count = 10) =>
    api.post(`/notebooks/sources/${sourceId}/generate_flashcards/`, { count }),
  generateQuiz: (sourceId: number, questionCount = 8) =>
    api.post(`/notebooks/sources/${sourceId}/generate_quiz/`, {
      question_count: questionCount,
    }),
  // The knowledge map: concepts with the caller's own mastery, and the
  // prerequisite links between them (found once, then cached).
  getMap: (id: number) => api.get<KnowledgeMapData>(`/notebooks/notebooks/${id}/map/`),
  // A map built from memory for one document: the student's own cards and
  // links, compared with that document's key points in one request.
  mapBuild: (id: number, body: { source: number; cards: { id: string; label: string }[]; links: BuildLink[] }) =>
    api.post<BuildResult>(`/notebooks/notebooks/${id}/map/build/`, body),
  findMapLinks: (id: number) =>
    api.post<{ edges: KnowledgeMapData['edges'] }>(`/notebooks/notebooks/${id}/map/links/`),
  practiseConcept: (id: number, concept: string) =>
    api.post<{ quiz_id: number; source_ids: number[] }>(`/notebooks/notebooks/${id}/map/practice/`, { concept }),
}

export type WeakConcept = {
  key: string
  label: string
  question_ids: number[]
  count: number
  sample: string[]
  // The live practice quiz already written for this concept, if any.
  practice_quiz_id: number | null
}

export const mockTestsAPI = {
  // Starting a test freezes its paper server-side, so a refresh cannot reshuffle it.
  // `planned_test`, when present, is how the server links this sitting back
  // to the plan it fulfils (stamping the plan's sat_at in the same
  // transaction) — without it the plan/sitting link is never made at all.
  start: (data: {
    notebook: number
    question_count?: number
    duration_minutes?: number
    planned_test?: number
    // The paper is exactly this notebook's mistake bank; question_count is ignored.
    mistakes_only?: boolean
  }) => api.post('/quizzes/mock-tests/', data),
  // Questions answered wrong and not yet answered right twice since — no answers included.
  mistakes: (notebook: number) =>
    api.get<{ count: number; questions: { id: number; question_text: string }[] }>(
      `/quizzes/mistakes/?notebook=${notebook}`
    ),
  // The mistake bank grouped into named concepts, biggest first.
  weakConcepts: (notebook: number) =>
    api.get<{ concepts: WeakConcept[] }>(`/quizzes/weak-concepts/?notebook=${notebook}`),
  // A fresh five-question quiz on one concept. 503 = no provider right now.
  practiceConcept: (data: { notebook: number; question_ids: number[]; label: string; key: string }) =>
    api.post<{ quiz_id: number; question_count: number; source_ids: number[] }>(
      '/quizzes/weak-concepts/practice/', data
    ),
  get: (id: number) => api.get(`/quizzes/mock-tests/${id}/`),
  // Deliberately returns no marking — feedback waits until the paper is handed in.
  answer: (id: number, paperQuestionId: number, answer: string) =>
    api.post(`/quizzes/mock-tests/${id}/answer/`, {
      paper_question_id: paperQuestionId,
      answer,
    }),
  submit: (id: number) => api.post(`/quizzes/mock-tests/${id}/submit/`, {}),
  // "Why?" on one wrong answer of a submitted paper. Stored server-side; 503 = no provider.
  explain: (id: number, paperQuestionId: number) =>
    api.post<{ id: number; explanation: string }>(`/quizzes/mock-tests/${id}/explain/`, {
      paper_question_id: paperQuestionId,
    }),
}

export const plannedTestsAPI = {
  list: () => api.get('/quizzes/planned-tests/'),
  create: (data: {
    notebook: number
    scheduled_for: string
    question_count?: number
    duration_minutes?: number
    reminder_lead_hours?: number
  }) => api.post('/quizzes/planned-tests/', data),
  remove: (id: number) => api.delete(`/quizzes/planned-tests/${id}/`),
}

export const analyticsAPI = {
  getSummary: () => api.get('/analytics/sessions/summary/'),
  // How much study is owed, plus per-document mastery — both derived from the
  // user's own record. Returns counts, never card questions.
  getRecommendations: () => api.get('/analytics/sessions/recommendations/'),
  getActivity: () => api.get('/analytics/sessions/activity/'),
}

export type ConceptState = 'strong' | 'shaky' | 'weak' | 'not_studied'
export type ConceptAction =
  | { kind: 'cards'; card_ids: number[] }
  | { kind: 'exercise'; exercise_id: number }
  | { kind: 'practice'; question_ids: number[] }
export type MapConcept = {
  key: string
  label: string
  point: string
  source_ids: number[]
  /** The key points it holds, as 'sourceId:index'. */
  members: string[]
  importance: 'core' | 'supporting'
  state: ConceptState
  understanding: { p: number; correct: number; total: number } | null
  /** Over the cards reviewed; `unseen` cards of the concept were never reviewed. */
  memory: { p: number; remembered: number; total: number; unseen: number } | null
  events: number
  action: ConceptAction | null
  first: string | null
  /** The name as the document wrote it, when `label` is a translation (lib/translate.ts). */
  original?: string
}
export type KnowledgeMapData = {
  concepts: MapConcept[]
  edges: { from: string; to: string; why: string }[]
  edges_status: 'ready' | 'missing' | 'none'
  missing_key_points: { source_id: number; title: string }[]
  unattached: number
}

export default api
