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

export const flashcardsAPI = {
  getFlashcards: (params?: any) => api.get('/flashcards/flashcards/', { params }),
  createFlashcard: (data: any) => api.post('/flashcards/flashcards/', data),
  updateFlashcard: (id: number, data: any) => api.put(`/flashcards/flashcards/${id}/`, data),
  deleteFlashcard: (id: number) => api.delete(`/flashcards/flashcards/${id}/`),
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
  getStudySessions: (params?: Record<string, unknown>) =>
    api.get('/analytics/sessions/', { params }),
  getRecommendations: (params?: { text?: string; limit?: number }) =>
    api.get('/analytics/sessions/recommendations/', { params }),
  getLearningPath: (params?: { subject?: string; limit?: number }) =>
    api.get('/analytics/sessions/learning_path/', { params }),
  getSubjects: () => api.get('/analytics/sessions/subjects/'),
  createStudySession: (data: {
    duration_minutes: number
    material_studied?: string
    notes?: string
    mood_before?: string
    mood_after?: string
  }) => api.post('/analytics/sessions/', data),
  updateStudySession: (id: number, data: Record<string, unknown>) =>
    api.put(`/analytics/sessions/${id}/`, data),
}


export default api
