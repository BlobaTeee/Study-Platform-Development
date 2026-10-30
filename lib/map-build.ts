// Building a notebook's map by hand: the links the student makes, before
// and after grading. The server checks the same rules (map_building.py).

export type BuildLink = { from: string; to: string; why: string }
export type Verdict = 'correct' | 'partial' | 'wrong' | 'unjudged'
export type GradedLink = BuildLink & { verdict: Verdict; feedback: string }
export type MissedLink = { from: string; to: string; why: string }

/** Must match MIN_WHY in backend/notebooks/services/map_building.py. */
export const MIN_WHY = 3

export function pairId(a: string, b: string): string {
  return [a, b].sort().join('|')
}

/** A link between two concepts, unless it is to itself or already made. */
export function addLink(links: BuildLink[], from: string, to: string): BuildLink[] {
  if (from === to || links.some((x) => pairId(x.from, x.to) === pairId(from, to))) return links
  return [...links, { from, to, why: '' }]
}

export function removeLink(links: BuildLink[], a: string, b: string): BuildLink[] {
  return links.filter((x) => pairId(x.from, x.to) !== pairId(a, b))
}

export function readyToSend(links: BuildLink[]): boolean {
  return links.length > 0 && links.every((x) => x.why.trim().length >= MIN_WHY)
}

export function tally(links: { verdict: Verdict }[]): Record<Verdict, number> {
  const out: Record<Verdict, number> = { correct: 0, partial: 0, wrong: 0, unjudged: 0 }
  for (const x of links) out[x.verdict] += 1
  return out
}
