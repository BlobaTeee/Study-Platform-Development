import axios from 'axios'
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

export const reviewsAPI = {
  // Reviews done and recall accuracy over the last 7 days — a real week window,
  // unlike the all-time counts on the analytics summary.
  getWeeklyStats: () => api.get('/study/card-reviews/stats/'),
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
  deleteSource: (id: number) => api.delete(`/notebooks/sources/${id}/`),
  uploadSource: (notebookId: number, file: File, title?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (title) form.append('title', title)
    return api.post(`/notebooks/notebooks/${notebookId}/upload_pdf/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
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


export default api
