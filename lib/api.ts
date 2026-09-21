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
}

export const materialsAPI = {
  getTopics: () => api.get('/materials/topics/'),
  getMaterials: (params?: any) => api.get('/materials/study-materials/', { params }),
  createMaterial: (data: any) => api.post('/materials/study-materials/', data),
  updateMaterial: (id: number, data: any) => api.put(`/materials/study-materials/${id}/`, data),
  deleteMaterial: (id: number) => api.delete(`/materials/study-materials/${id}/`),
}

/** How well you recalled a card, worst first. Drives the SM-2 schedule. */
export type ReviewGrade = 'hard' | 'good' | 'easy'

export const flashcardsAPI = {
  getFlashcards: (params?: any) => api.get('/flashcards/flashcards/', { params }),
  createFlashcard: (data: any) => api.post('/flashcards/flashcards/', data),
  updateFlashcard: (id: number, data: any) => api.put(`/flashcards/flashcards/${id}/`, data),
  deleteFlashcard: (id: number) => api.delete(`/flashcards/flashcards/${id}/`),
  // Self-graded review: the backend schedules the card's next appearance and
  // this is what analytics counts. No study session needed.
  recordReview: (flashcardId: number, result: ReviewGrade) =>
    api.post('/study/card-reviews/record/', { flashcard_id: flashcardId, result }),
  // Cards the SM-2 schedule says are owed today, plus ones never studied.
  // Cards scheduled ahead are deliberately withheld.
  getDueCards: () => api.get('/study/card-reviews/due_today/'),
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

export const notebooksAPI = {
  getNotebooks: () => api.get('/notebooks/notebooks/'),
  getNotebook: (id: number) => api.get(`/notebooks/notebooks/${id}/`),
  createNotebook: (data: { title: string; description?: string }) =>
    api.post('/notebooks/notebooks/', data),
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
  // appends, so the page needs this to say what a press will add to.
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
  get: (id: number) => api.get(`/quizzes/mock-tests/${id}/`),
  // Deliberately returns no marking — feedback waits until the paper is handed in.
  answer: (id: number, paperQuestionId: number, answer: string) =>
    api.post(`/quizzes/mock-tests/${id}/answer/`, {
      paper_question_id: paperQuestionId,
      answer,
    }),
  submit: (id: number) => api.post(`/quizzes/mock-tests/${id}/submit/`, {}),
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
