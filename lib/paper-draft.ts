'use client'

import { useSyncExternalStore } from 'react'
import { exercisesAPI, type PhotoQuestion } from '@/lib/api'

/** A paper brought to the mock-test page, from the moment its file is
 *  chosen until it is sat (2026-11-26). Kept outside the page so leaving it
 *  while the paper is read does not lose the reading, and saved to this
 *  browser once read so a reload still has it. Reading itself cannot outlive
 *  a reload: the request goes with the tab. */
export type PaperDraft = {
  /** Whose draft this is: another account on this browser starts empty. */
  owner: string
  reading: boolean
  title: string
  questions: PhotoQuestion[]
  /** Set when reading failed: the server's message, or a kind for the page to word. */
  error: { detail?: string; kind?: 'noProblem' | 'failed' } | null
}

const KEY = 'paper-draft'
const EMPTY: PaperDraft = { owner: '', reading: false, title: '', questions: [], error: null }

let state: PaperDraft = EMPTY
let loaded = false
const listeners = new Set<() => void>()

function load() {
  if (loaded || typeof window === 'undefined') return
  loaded = true
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? 'null')
    if (saved && Array.isArray(saved.questions) && typeof saved.owner === 'string') {
      state = { ...EMPTY, owner: saved.owner, title: String(saved.title ?? ''), questions: saved.questions }
    }
  } catch {
    /* private mode or a broken entry: start empty */
  }
}

function set(next: PaperDraft) {
  state = next
  try {
    if (next.questions.length) {
      localStorage.setItem(KEY, JSON.stringify({ owner: next.owner, title: next.title, questions: next.questions }))
    } else {
      localStorage.removeItem(KEY)
    }
  } catch {
    /* a paper with many figures can be over the browser's limit: kept in memory only */
  }
  listeners.forEach((l) => l())
}

function subscribe(listener: () => void) {
  load()
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** The draft of `owner` (the signed-in user's id), or an empty one. */
export function usePaperDraft(owner: string): PaperDraft {
  const draft = useSyncExternalStore(subscribe, () => (load(), state), () => EMPTY)
  return draft.owner === owner ? draft : { ...EMPTY, owner }
}

/** Read a file into a draft. Runs to the end even if the page is left. */
export async function readPaper(owner: string, file: File, fallbackTitle: string) {
  set({ owner, reading: true, title: fallbackTitle, questions: [], error: null })
  try {
    const res = (await exercisesAPI.readPhoto(file)).data
    set({ owner, reading: false, title: res.title || fallbackTitle, questions: res.questions, error: null })
  } catch (e) {
    const body = (e as { response?: { data?: { detail?: unknown; no_problem?: boolean } } }).response?.data
    set({
      owner, reading: false, title: fallbackTitle, questions: [],
      error: body?.no_problem ? { kind: 'noProblem' } : typeof body?.detail === 'string' ? { detail: body.detail } : { kind: 'failed' },
    })
  }
}

export function renameDraft(owner: string, title: string) {
  if (state.owner === owner) set({ ...state, title })
}

/** Done with it: sat, or put aside for another paper. */
export function clearDraft() {
  set(EMPTY)
}
