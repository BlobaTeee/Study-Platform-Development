/** Each of a document's key points, in order, with the mastery state of the
 *  concept that holds it (null when no concept does). Concepts name their
 *  key points as 'sourceId:index' (GET /notebooks/notebooks/<id>/map/). */
export function keyPointStates<S extends string>(
  concepts: { members: string[]; state: S }[],
  sourceId: number,
  count: number,
): (S | null)[] {
  const state = new Map<string, S>()
  for (const c of concepts) for (const m of c.members) state.set(m, c.state)
  return Array.from({ length: count }, (_, i) => state.get(`${sourceId}:${i}`) ?? null)
}
