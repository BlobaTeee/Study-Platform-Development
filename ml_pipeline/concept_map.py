"""The knowledge map's logic, with no Django and no model calls.

Concepts are the documents' key points, with the same idea in two documents
merged. Each card, question and practice problem is attached to the concept
it is closest to, by TF-IDF over words and characters (as subject_match),
among the concepts of its own documents. Links come from one model request
and are cleaned here. A concept's state is the weaker of its two signals,
understanding (BKT) and memory (FSRS), and the weaker one picks the action.
The thresholds are checked in notebooks/10_knowledge_map.ipynb.
"""
from __future__ import annotations

from .subject_match import _vectorise

MERGE_THRESHOLD = 0.45
ATTACH_THRESHOLD = 0.12
MAX_PREREQ = 3


def _text(c: dict) -> str:
    return f"{c.get('label', '')} {c.get('point', '')} {c.get('passage', '')}"


def merge_concepts(points: list[dict]) -> list[dict]:
    if not points:
        return []
    sims = (lambda m: (m @ m.T).toarray())(_vectorise([_text(p) for p in points]))
    concepts: list[dict] = []
    owner: dict[int, int] = {}
    for i, p in enumerate(points):
        best, best_sim = None, MERGE_THRESHOLD
        for j in range(i):
            c = concepts[owner[j]]
            if p['source_id'] in c['source_ids']:
                continue                      # one document's ideas stay apart
            if sims[i, j] >= best_sim:
                best, best_sim = owner[j], sims[i, j]
        if best is None:
            owner[i] = len(concepts)
            concepts.append({'key': p['key'], 'label': p['label'], 'point': p['point'], 'passage': p['passage'],
                             'source_ids': [p['source_id']], 'members': [p['key']],
                             'importance': p.get('importance', 'supporting')})
        else:
            owner[i] = best
            c = concepts[best]
            c['members'].append(p['key'])
            c['source_ids'].append(p['source_id'])
            if p.get('importance') == 'core':
                c['importance'] = 'core'
    return concepts


def attach(items: list[dict], concepts: list[dict], threshold: float = ATTACH_THRESHOLD) -> dict:
    out = {i['id']: None for i in items}
    if not items or not concepts:
        return out
    mat = _vectorise([_text(c) for c in concepts] + [i['text'] for i in items])
    sims = (mat[len(concepts):] @ mat[:len(concepts)].T).toarray()
    for row, item in enumerate(items):
        wanted = set(item.get('source_ids') or [])
        best, best_sim = None, threshold
        for col, c in enumerate(concepts):
            if wanted and not wanted & set(c['source_ids']):
                continue
            if sims[row, col] >= best_sim:
                best, best_sim = c['key'], sims[row, col]
        out[item['id']] = best
    return out


def _reaches(edges: list[tuple[int, int, str]], start: int, goal: int) -> bool:
    seen, todo = set(), [start]
    while todo:
        node = todo.pop()
        if node == goal:
            return True
        if node in seen:
            continue
        seen.add(node)
        todo.extend(b for a, b, _ in edges if a == node)
    return False


def clean_links(raw, n: int, max_prereq: int = MAX_PREREQ) -> list[tuple[int, int, str]]:
    edges: list[tuple[int, int, str]] = []
    count: dict[int, int] = {}
    for link in raw if isinstance(raw, list) else []:
        if not isinstance(link, dict):
            continue
        a, b = link.get('before'), link.get('after')
        if not (isinstance(a, int) and isinstance(b, int)) or isinstance(a, bool) or isinstance(b, bool):
            continue
        a, b = a - 1, b - 1
        if a == b or not (0 <= a < n and 0 <= b < n) or count.get(b, 0) >= max_prereq:
            continue
        if any(x == a and y == b for x, y, _ in edges) or _reaches(edges, b, a):
            continue                          # duplicate, or it would close a loop
        edges.append((a, b, str(link.get('why') or '')[:200]))
        count[b] = count.get(b, 0) + 1
    return edges


def weaker(understanding: float | None, memory: float | None) -> str | None:
    if understanding is None and memory is None:
        return None
    if memory is None:
        return 'understanding'
    if understanding is None:
        return 'memory'
    return 'memory' if memory < understanding else 'understanding'


def concept_state(understanding: float | None, memory: float | None, thresholds: dict) -> str:
    known = [v for v in (understanding, memory) if v is not None]
    if not known:
        return 'not_studied'
    low = min(known)
    return 'strong' if low >= thresholds['strong'] else 'shaky' if low >= thresholds['shaky'] else 'weak'


def choose_action(weak_side, card_ids, exercise_ids, question_ids) -> dict | None:
    if weak_side == 'understanding':
        if exercise_ids:
            return {'kind': 'exercise', 'exercise_id': exercise_ids[0]}
        if question_ids:
            return {'kind': 'practice', 'question_ids': list(question_ids)}
    if card_ids:
        return {'kind': 'cards', 'card_ids': list(card_ids)}
    if weak_side is None:
        return None
    if question_ids:
        return {'kind': 'practice', 'question_ids': list(question_ids)}
    return None

