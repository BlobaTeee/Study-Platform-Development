import axios from 'axios'
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
export type ReviewGrade = 'again' | 'hard' | 'good' | 'easy'

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

export const quizzesAPI = {
  getQuizzes: (params?: any) => api.get('/quizzes/quizzes/', { params }),
  getAttempts: () => api.get('/quizzes/attempts/'),
  createQuiz: (data: any) => api.post('/quizzes/quizzes/', data),
  startAttempt: (quizId: number) => api.post(`/quizzes/quizzes/${quizId}/start_attempt/`, {}),
  submitAnswer: (attemptId: number, data: any) => api.post(`/quizzes/attempts/${attemptId}/submit_answer/`, data),
  completeQuiz: (attemptId: number, data: any) => api.post(`/quizzes/attempts/${attemptId}/complete/`, data),
}

export const notebooksAPI = {
  getNotebooks: () => api.get('/notebooks/notebooks/'),
  getNotebook: (id: number) => api.get(`/notebooks/notebooks/${id}/`),
  createNotebook: (data: { title: string; description?: string }) =>
    api.post('/notebooks/notebooks/', data),
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

export const analyticsAPI = {
  getSummary: () => api.get('/analytics/sessions/summary/'),
  // How much study is owed, plus per-document mastery — both derived from the
  // user's own record. Returns counts, never card questions.
  getRecommendations: () => api.get('/analytics/sessions/recommendations/'),
}


export default api
