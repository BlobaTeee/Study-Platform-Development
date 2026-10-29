// Why a page's data did not load, so the page can say what actually happened
// instead of "cannot reach the server" for every failure. A 401 never gets
// here: lib/api.ts sends the reader to sign in first.

export type LoadFailure =
  | { kind: 'offline' }
  | { kind: 'server'; status: number }
  | { kind: 'other'; status: number | null }

export function loadFailure(error: unknown): LoadFailure {
  const e = error as { response?: { status?: number }; request?: unknown; code?: string } | null
  const status = e?.response?.status
  if (typeof status === 'number') {
    return status >= 500 ? { kind: 'server', status } : { kind: 'other', status }
  }
  // Sent but never answered: the backend is down, or the network is.
  if (e?.request !== undefined || e?.code === 'ERR_NETWORK') return { kind: 'offline' }
  return { kind: 'other', status: null }
}
