// The Progress page's "Cần ôn" list: everything a student should go back to,
// gathered per notebook from the four places that find it.

type Owed = { notebook_id: number; title: string; count: number }
type Forgotten = { notebook_id: number | null; title: string; count: number }
type MixUps<I> = { notebook_id: number; title: string; items: I[] }
type Practice = { notebook_id: number | null; title: string; total: number }

export type ReviewNotebook<F extends Forgotten, I, P extends Practice> = {
  key: string
  notebookId: number | null
  title: string
  owed: number
  forgotten: F | null
  mixUps: I[]
  practice: P | null
}

export function reviewSize(nb: { owed: number; forgotten: { count: number } | null; mixUps: unknown[]; practice: { total: number } | null }) {
  return nb.owed + (nb.forgotten?.count ?? 0) + nb.mixUps.length + (nb.practice?.total ?? 0)
}

/** One entry per notebook, biggest list first. Cards outside any notebook and
 *  the student's own practice problems are kept apart: both have no notebook,
 *  but they are different things. */
export function reviewNotebooks<F extends Forgotten, I, P extends Practice>(input: {
  owed: Owed[]
  forgotten: F[]
  mixUps: MixUps<I>[]
  practice: P[]
}): ReviewNotebook<F, I, P>[] {
  const byKey = new Map<string, ReviewNotebook<F, I, P>>()
  const entry = (key: string, notebookId: number | null, title: string) => {
    let nb = byKey.get(key)
    if (!nb) {
      nb = { key, notebookId, title, owed: 0, forgotten: null, mixUps: [], practice: null }
      byKey.set(key, nb)
    }
    if (!nb.title && title) nb.title = title
    return nb
  }
  for (const o of input.owed) if (o.count > 0) entry(`n${o.notebook_id}`, o.notebook_id, o.title).owed = o.count
  for (const f of input.forgotten) {
    if (f.count > 0) entry(f.notebook_id == null ? 'cards' : `n${f.notebook_id}`, f.notebook_id, f.title).forgotten = f
  }
  for (const m of input.mixUps) if (m.items.length) entry(`n${m.notebook_id}`, m.notebook_id, m.title).mixUps = m.items
  for (const p of input.practice) {
    if (p.total > 0) entry(p.notebook_id == null ? 'own' : `n${p.notebook_id}`, p.notebook_id, p.title).practice = p
  }
  return [...byKey.values()].sort((a, b) => reviewSize(b) - reviewSize(a) || a.title.localeCompare(b.title))
}
