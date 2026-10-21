# Knowledge Map Implementation Plan

> Work task by task, in order; each task ends green and committed. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** A per-notebook knowledge map: one card per concept, coloured by the
weaker of "understanding" (BKT) and "memory" (FSRS), joined by "needs this
first" arrows, with one action per concept.

**Architecture:** Pure logic lives in `ml_pipeline/` (BKT, concept merging,
attachment, link cleaning, state and action), unit-tested in `.venv`. A
backend service (`notebooks/services/knowledge_map.py`) gathers the
student's data and calls it; three `NotebookViewSet` actions serve the map,
find links (one model request) and start concept practice. The frontend lays
the map out deterministically (`lib/map-layout.ts`) and draws it with React
Flow inside the notebook page (`?view=map`).

**Tech Stack:** Django 5.2 + DRF, scikit-learn TF-IDF, scipy (BKT fit),
Next.js 16 + Tailwind v4 + next-intl, `@xyflow/react`.

**Spec:** `docs/specs/2026-10-20-knowledge-map-design.md`

## Global Constraints

- Keep the palette (mode colours blue/amber/violet/emerald), fonts (Fraunces / Open Sans / IBM Plex Mono), `.sheet` and `shadow-sheet`/`shadow-lift`; no side-stripe borders.
- Every UI string in both `messages/vi.json` and `messages/en.json` (`tests/test_messages_parity.py`).
- Commits: short conventional subject, no body, no co-author trailer, no AI-tool names in tracked files.
- No model call for mastery or attachment; links cost one request per notebook and are cached until the concepts change.
- Map access follows `notebooks_for(user)`; mastery is always the caller's own.
- ASSISTments raw data stays out of git (`datasets/raw/ASSISTments/*.parquet` is ignored).
- Suites: ML `.venv/bin/python -m pytest tests`; Django `cd backend && venv/bin/python -m pytest -c pytest.ini`; frontend `pnpm test`, `npx tsc --noEmit -p .`.

## Review Focus

1. A notebook where only some documents have key points: the map shows those concepts and names the documents without key points (Task 5 test).
2. A concept with nothing attached yet: grey "not studied", and an action only if it has cards to start (Task 3 and Task 5 tests).
3. A shared notebook: a member sees their own mastery, not the owner's (Task 5 test).
4. A link reply that is malformed, names unknown concepts, loops, or fails outright: the map still loads, edges are cleaned or marked unavailable, never a 500 (Task 6 tests).
5. A notebook with 40+ concepts and no links yet: the layout wraps into columns without overlap instead of one tall column (Task 7 test).

---

### Task 1: BKT core

**Files:**
- Create: `ml_pipeline/bkt.py`
- Create: `ml_pipeline/models/bkt.json` (literature defaults; Task 2 overwrites with fitted values)
- Test: `tests/test_bkt.py`

**Interfaces:**
- Produces: `Params` (dataclass: `init, learn, slip, guess_choice, guess_written`), `kind_of(answer_type: str) -> 'choice'|'written'`, `p_correct(p_known, kind, params) -> float`, `update(p_known, correct: bool, kind, params) -> float`, `trace(events: list[tuple[bool, str]], params) -> float`, `neg_log_likelihood(sequences, params) -> float`, `fit(sequences) -> Params`, `load() -> tuple[Params, dict]` (params, thresholds `{'strong': float, 'shaky': float}`).

- [ ] **Step 1: Write the failing tests**

```python
"""Bayesian Knowledge Tracing: the chance a skill is known, after each answer."""
import random

from ml_pipeline.bkt import Params, fit, kind_of, load, neg_log_likelihood, p_correct, trace, update

P = Params(init=0.3, learn=0.2, slip=0.1, guess_choice=0.25, guess_written=0.1)


def test_a_right_answer_raises_the_chance_and_a_wrong_one_lowers_it():
    assert update(0.5, True, 'choice', P) > 0.5
    assert update(0.5, False, 'choice', P) < 0.5 + P.learn


def test_a_right_multiple_choice_answer_counts_for_less_than_a_written_one():
    # Guessing a 1-in-4 option is easier than guessing a written answer.
    assert update(0.3, True, 'choice', P) < update(0.3, True, 'written', P)


def test_p_correct_mixes_knowing_and_guessing():
    assert p_correct(1.0, 'written', P) == 1 - P.slip
    assert p_correct(0.0, 'choice', P) == P.guess_choice


def test_trace_of_nothing_is_the_prior_and_a_run_of_right_answers_approaches_one():
    assert trace([], P) == P.init
    assert trace([(True, 'written')] * 8, P) > 0.95


def test_answer_types_map_to_two_kinds():
    assert kind_of('choose_1') == 'choice' and kind_of('choose_n') == 'choice'
    assert kind_of('algebra') == 'written' and kind_of('fill_in_1') == 'written'


def test_fit_recovers_parameters_from_simulated_students():
    rng = random.Random(3)
    true = Params(init=0.2, learn=0.25, slip=0.08, guess_choice=0.3, guess_written=0.05)
    seqs = []
    for _ in range(400):
        known = rng.random() < true.init
        seq = []
        for _ in range(10):
            kind = 'choice' if rng.random() < 0.5 else 'written'
            guess = true.guess_choice if kind == 'choice' else true.guess_written
            right = (rng.random() > true.slip) if known else (rng.random() < guess)
            seq.append((right, kind))
            known = known or rng.random() < true.learn
        seqs.append(seq)
    got = fit(seqs)
    assert abs(got.learn - true.learn) < 0.08 and abs(got.guess_choice - true.guess_choice) < 0.08
    assert neg_log_likelihood(seqs, got) <= neg_log_likelihood(seqs, P)


def test_shipped_parameters_load_with_thresholds():
    params, thresholds = load()
    assert 0 < params.init < 1 and thresholds['strong'] > thresholds['shaky']
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_bkt.py -q`
Expected: FAIL, `ModuleNotFoundError: ml_pipeline.bkt`

- [ ] **Step 3: Implement**

```python
"""Bayesian Knowledge Tracing: how likely a student knows a concept, from the
order in which they answered questions on it.

Corbett & Anderson (1995). A concept is known or not; each answer is right
with probability 1 - slip if known and guess if not; after each answer the
student may learn it (learn). Guessing a four-option question is easier
than guessing a written answer, so the two kinds get their own guess. The
parameters are fitted on ASSISTments 2009 in notebooks/10_knowledge_map.ipynb
and kept in models/bkt.json. No Django imports.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

PATH = Path(__file__).resolve().parent / 'models' / 'bkt.json'
CHOICE_TYPES = {'choose_1', 'choose_n', 'choice'}
BOUNDS = {'init': (0.01, 0.99), 'learn': (0.01, 0.6), 'slip': (0.01, 0.3),
          'guess_choice': (0.01, 0.5), 'guess_written': (0.01, 0.3)}
EPS = 1e-6


@dataclass(frozen=True)
class Params:
    init: float
    learn: float
    slip: float
    guess_choice: float
    guess_written: float

    def guess(self, kind: str) -> float:
        return self.guess_choice if kind == 'choice' else self.guess_written


def kind_of(answer_type: str) -> str:
    return 'choice' if answer_type in CHOICE_TYPES else 'written'


def p_correct(p_known: float, kind: str, params: Params) -> float:
    return p_known * (1 - params.slip) + (1 - p_known) * params.guess(kind)


def update(p_known: float, correct: bool, kind: str, params: Params) -> float:
    g, s = params.guess(kind), params.slip
    if correct:
        post = p_known * (1 - s) / max(EPS, p_known * (1 - s) + (1 - p_known) * g)
    else:
        post = p_known * s / max(EPS, p_known * s + (1 - p_known) * (1 - g))
    return post + (1 - post) * params.learn


def trace(events, params: Params) -> float:
    p = params.init
    for correct, kind in events:
        p = update(p, bool(correct), kind, params)
    return p


def neg_log_likelihood(sequences, params: Params) -> float:
    total = 0.0
    for seq in sequences:
        p = params.init
        for correct, kind in seq:
            q = min(1 - EPS, max(EPS, p_correct(p, kind, params)))
            total -= math.log(q if correct else 1 - q)
            p = update(p, correct, kind, params)
    return total


def fit(sequences) -> Params:
    from scipy.optimize import minimize
    names = list(BOUNDS)
    start = [0.3, 0.15, 0.1, 0.25, 0.1]
    res = minimize(lambda x: neg_log_likelihood(sequences, Params(*x)), start, method='L-BFGS-B',
                   bounds=[BOUNDS[n] for n in names])
    return Params(*[float(v) for v in res.x])


def save(params: Params, thresholds: dict, path: Path = PATH, **extra) -> None:
    path.write_text(json.dumps({'params': asdict(params), 'thresholds': thresholds, **extra}, indent=1) + '\n')


def load(path: Path = PATH) -> tuple[Params, dict]:
    doc = json.loads(path.read_text())
    return Params(**doc['params']), doc['thresholds']
```

`ml_pipeline/models/bkt.json` (defaults until Task 2):

```json
{
 "params": {"init": 0.3, "learn": 0.15, "slip": 0.1, "guess_choice": 0.25, "guess_written": 0.1},
 "thresholds": {"strong": 0.8, "shaky": 0.5},
 "source": "defaults; replaced by notebooks/10_knowledge_map.ipynb"
}
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_bkt.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/bkt.py ml_pipeline/models/bkt.json tests/test_bkt.py
git commit -m "feat(ml): bayesian knowledge tracing with a guess per answer kind"
```

---

### Task 2: Notebook 10, part 1 (BKT on ASSISTments)

**Files:**
- Create: `ml_pipeline/notebooks/10_knowledge_map.ipynb` (built by a scratchpad script with `nbformat`, executed with `jupyter nbconvert --execute --inplace`)
- Modify: `ml_pipeline/models/bkt.json` (written by the notebook)
- Modify: `datasets/README.md` (ASSISTments entry)

**Interfaces:**
- Consumes: `ml_pipeline.bkt.fit, trace, p_correct, kind_of, save`.
- Produces: fitted `models/bkt.json` with `params`, `thresholds`, `auc`, `baseline_auc`.

- [ ] **Step 1: Notebook cells**

1. Markdown: the problem (two signals, BKT for understanding), the data (ASSISTments 2009–2010 skill builder, Feng, Heffernan & Koedinger 2009; mirror `Atomi/ASSISTments2009`; 4,148 students, 274,331 responses, 139 skills), the split by student 80/20 with `config.RANDOM_SEED`.
2. Code: load `datasets/raw/ASSISTments/assist2009.parquet`; build sequences per (student, skill) of `(grade == '1', kind_of(answer_type))`; drop `open_response`.
3. Code: `fit` on train sequences (subsample 1,500 students if a fit takes over 3 minutes; say so in the output).
4. Code: AUC on test of predicting each next answer: BKT `p_correct(p, kind)` before the answer vs. the baseline "running accuracy on that skill with a 0.6 prior" (`sklearn.metrics.roc_auc_score`).
5. Code: thresholds: on test, bucket each prediction-time `p_known` into strong/shaky/weak with candidate cut-offs (0.7/0.4, 0.8/0.5, 0.9/0.6); show the next-answer accuracy per bucket; keep 0.8/0.5 unless another pair separates the buckets clearly better (state the rule in markdown before the cell).
6. Code: `save(params, thresholds, auc=..., baseline_auc=..., source='ASSISTments 2009, notebooks/10_knowledge_map.ipynb')`.
7. Markdown: results and limits (maths skills of middle-school students, not university subjects; the weaker-signal rule is a design choice, not fitted).

- [ ] **Step 2: Execute and check**

Run: `cd ml_pipeline/notebooks && ../../.venv/bin/jupyter nbconvert --to notebook --execute --inplace 10_knowledge_map.ipynb`
Expected: BKT AUC above the baseline; `bkt.json` rewritten; `.venv/bin/python -m pytest tests/test_bkt.py -q` still 7 passed.

- [ ] **Step 3: README entry** (in `datasets/README.md`, before "## Integrity check")

```markdown
### ASSISTments 2009–2010 skill builder  (knowledge map: BKT)

- **Source:** Feng, M., Heffernan, N. & Koedinger, K. (2009). *Addressing the assessment challenge
  with an online system that tutors as it assesses.* UMUAI 19(3). Per-student sequences from the
  Hugging Face mirror `Atomi/ASSISTments2009`.
- **Licence:** free for research use with citation of the paper above.
- **Committed:** ⛔ no (gitignored). Download into `datasets/raw/ASSISTments/`:

  ```bash
  curl -L -o datasets/raw/ASSISTments/assist2009.parquet \
    "https://huggingface.co/datasets/Atomi/ASSISTments2009/resolve/main/data/train-00000-of-00001.parquet"
  ```
- **Schema:** one row per student: `skill_ids`, `skill_names`, `grades` ('1' right, '0' wrong),
  `attempt_counts`, `answer_types` (`algebra`, `choose_1`, `fill_in_1`, ...), in answer order.
- **Used by:** `ml_pipeline/notebooks/10_knowledge_map.ipynb` (fits `ml_pipeline/models/bkt.json`).
```

- [ ] **Step 4: Commit**

```bash
git add ml_pipeline/notebooks/10_knowledge_map.ipynb ml_pipeline/models/bkt.json datasets/README.md
git commit -m "feat(ml): fit knowledge tracing on ASSISTments (notebook 10)"
```

---

### Task 3: Concept map logic

**Files:**
- Create: `ml_pipeline/concept_map.py`
- Test: `tests/test_concept_map.py`

**Interfaces:**
- Consumes: `ml_pipeline.subject_match._vectorise`.
- Produces:
  - `merge_concepts(points: list[dict]) -> list[dict]`; input `{key, source_id, label, point, passage, importance}`, output `{key, label, point, passage, source_ids: list[int], members: list[str], importance}` in input order of first members.
  - `attach(items: list[dict], concepts: list[dict], threshold=ATTACH_THRESHOLD) -> dict[str, str | None]`; item `{id: str, text, source_ids: list[int]}`.
  - `clean_links(raw, n: int, max_prereq=3) -> list[tuple[int, int, str]]`; raw `[{"before": i, "after": j, "why": str}]`, 1-based indices into the concept list; returns 0-based `(before, after, why)`.
  - `concept_state(understanding: float | None, memory: float | None, thresholds: dict) -> str` in `'strong'|'shaky'|'weak'|'not_studied'`.
  - `weaker(understanding, memory) -> 'understanding'|'memory'|None`.
  - `choose_action(weak_side, card_ids, exercise_ids, question_ids) -> dict | None`: `{'kind': 'cards', 'card_ids': [...]}` | `{'kind': 'exercise', 'exercise_id': int}` | `{'kind': 'practice', 'question_ids': [...]}`.
  - Constants `MERGE_THRESHOLD = 0.55`, `ATTACH_THRESHOLD = 0.12` (Task 9 checks them).

- [ ] **Step 1: Write the failing tests**

```python
"""The knowledge map's logic: concepts, attachment, links, state, action."""
from ml_pipeline.concept_map import (
    attach, choose_action, clean_links, concept_state, merge_concepts, weaker,
)

T = {'strong': 0.8, 'shaky': 0.5}


def kp(key, source_id, label, passage):
    return {'key': key, 'source_id': source_id, 'label': label, 'point': label, 'passage': passage,
            'importance': 'core'}


def test_the_same_idea_in_two_documents_is_one_concept():
    concepts = merge_concepts([
        kp('1:0', 1, 'Covalent bonding', 'Atoms share pairs of electrons in a covalent bond.'),
        kp('2:3', 2, 'Covalent bonds', 'A covalent bond forms when two atoms share a pair of electrons.'),
        kp('1:1', 1, 'Acids and bases', 'Acids donate protons; bases accept protons.'),
    ])
    assert [c['members'] for c in concepts] == [['1:0', '2:3'], ['1:1']]
    assert concepts[0]['source_ids'] == [1, 2]


def test_two_ideas_in_one_document_are_never_merged():
    concepts = merge_concepts([kp('1:0', 1, 'Covalent bonding', 'Atoms share electrons.'),
                               kp('1:1', 1, 'Covalent bonding', 'Atoms share electrons.')])
    assert len(concepts) == 2


def test_an_item_goes_to_its_closest_concept_among_its_own_sources():
    concepts = merge_concepts([kp('1:0', 1, 'Acids', 'An acid donates a proton to a base in water.'),
                               kp('1:1', 1, 'Enzymes', 'Enzymes are proteins that speed up reactions.'),
                               kp('2:0', 2, 'Acids', 'An acid donates a proton.')])
    got = attach([{'id': 'card:5', 'text': 'What does an acid donate? A proton', 'source_ids': [1]},
                  {'id': 'q:9', 'text': 'Which molecules speed reactions? Enzymes', 'source_ids': [1]},
                  {'id': 'q:10', 'text': 'Photosynthesis in leaves', 'source_ids': [1]}], concepts)
    assert got['card:5'] == concepts[0]['key'] and got['q:9'] == concepts[1]['key']
    assert got['q:10'] is None


def test_links_keep_known_pairs_drop_self_unknown_and_loops():
    raw = [{'before': 1, 'after': 2, 'why': 'a'}, {'before': 2, 'after': 3, 'why': 'b'},
           {'before': 3, 'after': 1, 'why': 'loop'}, {'before': 2, 'after': 2, 'why': 'self'},
           {'before': 9, 'after': 1, 'why': 'unknown'}, 'junk', {'before': '1', 'after': 3}]
    assert clean_links(raw, 3) == [(0, 1, 'a'), (1, 2, 'b')]


def test_a_concept_keeps_at_most_three_prerequisites():
    raw = [{'before': i, 'after': 5, 'why': str(i)} for i in (1, 2, 3, 4)]
    assert len(clean_links(raw, 5)) == 3


def test_state_is_the_weaker_signal_and_none_means_not_studied():
    assert concept_state(0.9, 0.3, T) == 'weak'
    assert concept_state(0.9, None, T) == 'strong'
    assert concept_state(None, 0.6, T) == 'shaky'
    assert concept_state(None, None, T) == 'not_studied'
    assert weaker(0.9, 0.3) == 'memory' and weaker(0.4, 0.9) == 'understanding' and weaker(None, None) is None


def test_the_action_follows_the_weaker_side():
    assert choose_action('memory', [3, 4], [], [7]) == {'kind': 'cards', 'card_ids': [3, 4]}
    assert choose_action('understanding', [3], [11], [7]) == {'kind': 'exercise', 'exercise_id': 11}
    assert choose_action('understanding', [3], [], [7, 8]) == {'kind': 'practice', 'question_ids': [7, 8]}
    assert choose_action('understanding', [3], [], []) == {'kind': 'cards', 'card_ids': [3]}


def test_a_concept_never_studied_starts_with_its_cards_or_nothing():
    assert choose_action(None, [3], [], [7]) == {'kind': 'cards', 'card_ids': [3]}
    assert choose_action(None, [], [], []) is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_concept_map.py -q`
Expected: FAIL, `ModuleNotFoundError: ml_pipeline.concept_map`

- [ ] **Step 3: Implement**

```python
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

MERGE_THRESHOLD = 0.55
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
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_concept_map.py -q`
Expected: 8 passed. If the merge or attach test fails on similarity, print `sims` for that case and adjust `MERGE_THRESHOLD`/`ATTACH_THRESHOLD` only within 0.4–0.7 / 0.08–0.2; Task 9 settles them on real data.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/concept_map.py tests/test_concept_map.py
git commit -m "feat(ml): concept merging, attachment, link cleaning and concept state"
```

---

### Task 4: Retrievability today, shared with the forecast

**Files:**
- Modify: `backend/study_sessions/forecast.py`
- Test: `backend/tests/test_forecast.py` (append)

**Interfaces:**
- Produces: `retrievability_today(user, card_ids) -> dict[int, float]` (reviewed cards only), used by Task 5. `forecast()` keeps its output.

- [ ] **Step 1: Failing test** (append; reuse the file's existing fixtures for a card and reviews)

```python
def test_retrievability_today_covers_only_reviewed_cards(user, notebook):
    from flashcards.models import Flashcard
    from study_sessions.forecast import retrievability_today
    from study_sessions.models import CardReview
    seen = Flashcard.objects.create(user=user, notebook=notebook, question='Q1?', answer='A')
    unseen = Flashcard.objects.create(user=user, notebook=notebook, question='Q2?', answer='A')
    CardReview.record(user, seen, 'good')

    got = retrievability_today(user, [seen.id, unseen.id])

    assert set(got) == {seen.id} and 0.9 < got[seen.id] <= 1.0
```

- [ ] **Step 2:** Run `cd backend && venv/bin/python -m pytest -c pytest.ini tests/test_forecast.py -q`; expected FAIL (ImportError).

- [ ] **Step 3: Implement** — move the review-loading lines of `forecast()` into:

```python
def _histories(user, card_ids) -> dict:
    reviews: dict[int, list] = {}
    for card_id, result, when in (CardReview.objects.grades()
                                  .filter(user=user, flashcard_id__in=list(card_ids))
                                  .values_list('flashcard_id', 'result', 'review_date')):
        if result in RATING:
            reviews.setdefault(card_id, []).append((when, RATING[result]))
    return {card_id: replay(r) for card_id, r in reviews.items()}


def retrievability_today(user, card_ids) -> dict[int, float]:
    """The chance each reviewed card is recalled right now (FSRS-6)."""
    now = timezone.now()
    return {cid: retrievability((now - s.last_review).total_seconds() / 86400, s.stability)
            for cid, s in _histories(user, card_ids).items()}
```

and in `forecast()` replace the `reviews` loop and `history = ...` with `history = _histories(user, card_notebook)`.

- [ ] **Step 4:** Run `tests/test_forecast.py`; expected all pass, the old forecast tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/study_sessions/forecast.py backend/tests/test_forecast.py
git commit -m "refactor(study): share card retrievability with the knowledge map"
```

---

### Task 5: The map endpoint

**Files:**
- Create: `backend/notebooks/services/knowledge_map.py`
- Modify: `backend/notebooks/models.py` (add `Notebook.concept_links = models.JSONField(blank=True, default=dict)`)
- Create: `backend/notebooks/migrations/0011_notebook_concept_links.py` (`makemigrations notebooks -n notebook_concept_links`)
- Modify: `backend/notebooks/views.py` (action `knowledge_map`)
- Test: `backend/tests/test_knowledge_map.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4; `study_sessions.views.studiable_cards`; models `Question`, `Answer`, `MockTestQuestion`, `Exercise`, `ExerciseAttempt`.
- Note: the spec caches mastery per user and notebook. The plan caches only the
  attachment (the TF-IDF part, shared by every student of the notebook) and
  computes mastery per request; add a per-user cache only if `build_map`
  measures over 300 ms on the demo account (time it in Task 9).
- Produces: `concepts_of(notebook) -> list[dict]` (merged concepts, plus `index` 1-based), `concepts_hash(concepts) -> str`, `build_map(user, notebook) -> dict`:

```
{"concepts": [{"key", "label", "point", "source_ids", "importance", "state",
               "understanding": {"p", "correct", "total"} | null,
               "memory": {"p", "remembered", "total"} | null,
               "events": int, "action": {...} | null, "first": key | null}],
 "edges": [{"from": key, "to": key, "why": str}],
 "edges_status": "ready" | "missing" | "none",
 "missing_key_points": [{"source_id", "title"}],
 "unattached": int}
```
`edges_status`: `none` with fewer than 2 concepts; `ready` when `notebook.concept_links['hash'] == concepts_hash(...)`; else `missing`.
- Route: `GET /api/notebooks/notebooks/<id>/map/`.

- [ ] **Step 1: Failing tests**

```python
"""The knowledge map: concepts from key points, the student's own signals."""
import pytest

from flashcards.models import Flashcard
from notebooks.models import NotebookMember, Source
from quizzes.models import Answer, Question, Quiz, QuizAttempt
from study_sessions.models import CardReview
from tests.conftest import make_source

pytestmark = pytest.mark.django_db
MAP = '/api/notebooks/notebooks/{}/map/'
ACID = 'An acid donates a proton to a base when the two react in water.'
ENZ = 'Enzymes are proteins that speed up chemical reactions in cells.'


@pytest.fixture
def chem(user):
    from notebooks.models import Notebook
    nb = Notebook.objects.create(user=user, title='Chemistry')
    src = make_source(nb, 'Reactions', (ACID + ' ' + ENZ + ' ') * 30)
    src.key_points = [{'point': 'Acids donate protons', 'label': 'Acids', 'importance': 'core', 'passage': ACID},
                      {'point': 'Enzymes speed reactions', 'label': 'Enzymes', 'importance': 'core', 'passage': ENZ}]
    src.save()
    make_source(nb, 'Notes')                          # no key points yet
    return nb, src


def _card(user, nb, src, q, a):
    card = Flashcard.objects.create(user=user, notebook=nb, question=q, answer=a)
    card.sources.set([src])
    return card


def test_concepts_come_from_key_points_and_documents_without_them_are_named(client, chem):
    nb, src = chem
    body = client.get(MAP.format(nb.id)).json()
    assert [c['label'] for c in body['concepts']] == ['Acids', 'Enzymes']
    assert [m['title'] for m in body['missing_key_points']] == ['Notes']
    assert body['edges_status'] == 'missing'
    assert all(c['state'] == 'not_studied' and c['action'] is None for c in body['concepts'])


def test_cards_give_memory_and_answers_give_understanding(client, user, chem):
    nb, src = chem
    card = _card(user, nb, src, 'What does an acid donate to a base?', 'A proton')
    CardReview.record(user, card, 'good')
    quiz = Quiz.objects.create(user=user, title='Q', is_published=True)
    q = Question.objects.create(quiz=quiz, source=src, source_excerpt=ENZ, question_text='What speeds reactions?',
                                question_type='multiple_choice', options=['Enzymes', 'Salt', 'Ice', 'Sand'],
                                correct_answer='Enzymes')
    att = QuizAttempt.objects.create(quiz=quiz, user=user)
    Answer.objects.create(quiz_attempt=att, question=q, user_answer='Salt', is_correct=False)

    by = {c['label']: c for c in client.get(MAP.format(nb.id)).json()['concepts']}

    assert by['Acids']['memory']['total'] == 1 and by['Acids']['understanding'] is None
    assert by['Acids']['action'] == {'kind': 'cards', 'card_ids': [card.id]}
    assert by['Enzymes']['understanding'] == {'p': pytest.approx(by['Enzymes']['understanding']['p']),
                                              'correct': 0, 'total': 1}
    assert by['Enzymes']['state'] in ('weak', 'shaky')
    assert by['Enzymes']['action'] == {'kind': 'practice', 'question_ids': [q.id]}


def test_a_member_sees_their_own_mastery(client, other_client, user, other_user, chem):
    nb, src = chem
    NotebookMember.objects.create(notebook=nb, user=other_user, role='member')
    card = _card(user, nb, src, 'What does an acid donate?', 'A proton')
    CardReview.record(user, card, 'good')

    theirs = {c['label']: c for c in other_client.get(MAP.format(nb.id)).json()['concepts']}

    assert theirs['Acids']['memory'] is None and theirs['Acids']['state'] == 'not_studied'


def test_a_stranger_gets_404(other_client, chem):
    nb, _ = chem
    assert other_client.get(MAP.format(nb.id)).status_code == 404


def test_cached_links_count_only_for_the_same_concepts(client, chem):
    from notebooks.services.knowledge_map import concepts_hash, concepts_of
    nb, src = chem
    nb.concept_links = {'hash': concepts_hash(concepts_of(nb)),
                        'edges': [{'from': f'{src.id}:0', 'to': f'{src.id}:1', 'why': 'acids first'}]}
    nb.save()
    body = client.get(MAP.format(nb.id)).json()
    assert body['edges_status'] == 'ready' and body['edges'][0]['why'] == 'acids first'
    src.key_points = src.key_points[:1]
    src.save()
    assert client.get(MAP.format(nb.id)).json()['edges_status'] == 'none'
```

- [ ] **Step 2:** Run `venv/bin/python -m pytest -c pytest.ini tests/test_knowledge_map.py -q`; expected FAIL (404 on the route).

- [ ] **Step 3: Implement**

`backend/notebooks/services/knowledge_map.py`:

```python
"""The knowledge map of one notebook for one student.

Concepts are the documents' key points (merged across documents); each card,
question and practice problem is attached to one (ml_pipeline.concept_map).
Understanding is BKT over the student's answers and submits on a concept's
questions and problems; memory is FSRS retrievability today of its cards.
The colour is the weaker of the two. No model call here: links are found
separately (find_links) and cached on the notebook.
"""
import hashlib

from django.core.cache import cache

from ml_pipeline import bkt
from ml_pipeline.concept_map import attach, choose_action, concept_state, merge_concepts, weaker

ATTACH_TTL = 60 * 60


def concepts_of(notebook) -> list[dict]:
    points = []
    for src in notebook.sources.filter(status='ready').order_by('created_at', 'id').only('id', 'key_points'):
        for i, kp in enumerate(src.key_points or []):
            points.append({'key': f'{src.id}:{i}', 'source_id': src.id, 'label': kp.get('label') or kp.get('point', ''),
                           'point': kp.get('point', ''), 'passage': kp.get('passage', ''),
                           'importance': kp.get('importance', 'supporting')})
    concepts = merge_concepts(points)
    for n, c in enumerate(concepts, 1):
        c['index'] = n
    return concepts


def concepts_hash(concepts) -> str:
    return hashlib.sha1('|'.join(sorted(c['key'] for c in concepts)).encode()).hexdigest()[:16]


def _items(user, notebook):
    from exercises.models import Exercise
    from quizzes.models import Question
    from study_sessions.views import studiable_cards

    cards = list(studiable_cards(user).filter(notebook=notebook).prefetch_related('sources'))
    questions = list(Question.objects.filter(source__notebook=notebook).only('id', 'source_id', 'source_excerpt',
                                                                              'question_text', 'question_type'))
    exercises = list(Exercise.objects.filter(user=user, notebook=notebook))
    items = ([{'id': f'card:{c.id}', 'text': f'{c.question} {c.answer}', 'source_ids': [s.id for s in c.sources.all()]}
              for c in cards]
             + [{'id': f'q:{q.id}', 'text': q.source_excerpt or q.question_text,
                 'source_ids': [q.source_id] if q.source_id else []} for q in questions]
             + [{'id': f'ex:{e.id}', 'text': ' '.join(cp.get('basis', '') for cp in e.reference.get('checkpoints', []))
                 or e.prompt, 'source_ids': [e.source_id] if e.source_id else []} for e in exercises])
    return cards, questions, exercises, items


def _attached(notebook, concepts, items) -> dict:
    sig = hashlib.sha1((concepts_hash(concepts) + '|'.join(sorted(i['id'] for i in items))).encode()).hexdigest()
    key = f'map-attach:{notebook.id}:{sig}'
    got = cache.get(key)
    if got is None:
        got = attach(items, concepts)
        cache.set(key, got, ATTACH_TTL)
    return got


def _events(user, question_ids, exercise_ids) -> dict[str, list]:
    """Each item's answers in time order: {'q:7': [(when, correct, kind)], 'ex:3': [...]}"""
    from exercises.models import ExerciseAttempt
    from quizzes.models import Answer, MockTestQuestion
    out: dict[str, list] = {}
    for qid, ok, when, mode in Answer.objects.filter(quiz_attempt__user=user, question_id__in=question_ids) \
            .values_list('question_id', 'is_correct', 'answered_at', 'mode'):
        out.setdefault(f'q:{qid}', []).append((when, bool(ok), 'written' if mode == 'typed' else 'choice'))
    for qid, ok, when in MockTestQuestion.objects.filter(mock_test__user=user, question_id__in=question_ids,
                                                         is_correct__isnull=False, answered_at__isnull=False) \
            .values_list('question_id', 'is_correct', 'answered_at'):
        out.setdefault(f'q:{qid}', []).append((when, bool(ok), 'choice'))
    for eid, result, when in ExerciseAttempt.objects.filter(exercise_id__in=exercise_ids, kind='submit') \
            .values_list('exercise_id', 'result', 'created_at'):
        out.setdefault(f'ex:{eid}', []).append((when, result.get('verdict') == 'passed', 'written'))
    return out


def build_map(user, notebook) -> dict:
    from study_sessions.forecast import retrievability_today

    concepts = concepts_of(notebook)
    cards, questions, exercises, items = _items(user, notebook)
    where = _attached(notebook, concepts, items)
    params, thresholds = bkt.load()
    events = _events(user, [q.id for q in questions], [e.id for e in exercises])
    recall = retrievability_today(user, [c.id for c in cards])

    members: dict[str, dict] = {c['key']: {'cards': [], 'questions': [], 'exercises': []} for c in concepts}
    for item_id, concept in where.items():
        if concept is None:
            continue
        kind, pk = item_id.split(':')
        members[concept][{'card': 'cards', 'q': 'questions', 'ex': 'exercises'}[kind]].append(int(pk))

    out = []
    for c in concepts:
        m = members[c['key']]
        evs = sorted((e for i in [f'q:{q}' for q in m['questions']] + [f'ex:{x}' for x in m['exercises']]
                      for e in events.get(i, [])), key=lambda e: e[0])
        understanding = ({'p': round(bkt.trace([(ok, kind) for _, ok, kind in evs], params), 3),
                          'correct': sum(ok for _, ok, _ in evs), 'total': len(evs)} if evs else None)
        reviewed = [recall[i] for i in m['cards'] if i in recall]
        memory = ({'p': round(sum(reviewed) / len(reviewed), 3), 'remembered': round(sum(reviewed)),
                   'total': len(m['cards'])} if reviewed else None)
        u, mem = (understanding or {}).get('p'), (memory or {}).get('p')
        weakest_cards = sorted(m['cards'], key=lambda i: recall.get(i, 0.0))
        out.append({'key': c['key'], 'label': c['label'], 'point': c['point'], 'source_ids': c['source_ids'],
                    'importance': c['importance'], 'state': concept_state(u, mem, thresholds),
                    'understanding': understanding, 'memory': memory,
                    'events': len(evs) + len(reviewed),
                    'action': choose_action(weaker(u, mem), weakest_cards, m['exercises'], m['questions']),
                    'first': None})

    edges, status = [], 'none' if len(concepts) < 2 else 'missing'
    links = notebook.concept_links or {}
    if len(concepts) >= 2 and links.get('hash') == concepts_hash(concepts):
        status, edges = 'ready', links.get('edges', [])
    rank = {'weak': 0, 'shaky': 1}
    by_key = {c['key']: c for c in out}
    for c in out:
        prereqs = [by_key[e['from']] for e in edges if e['to'] == c['key'] and e['from'] in by_key]
        shaky = sorted((p for p in prereqs if p['state'] in rank), key=lambda p: rank[p['state']])
        c['first'] = shaky[0]['key'] if shaky and c['state'] != 'strong' else None

    missing = [{'source_id': s.id, 'title': s.title}
               for s in notebook.sources.filter(status='ready').order_by('created_at', 'id').only('id', 'title',
                                                                                                  'key_points')
               if not s.key_points]
    return {'concepts': out, 'edges': edges, 'edges_status': status, 'missing_key_points': missing,
            'unattached': sum(1 for v in where.values() if v is None)}
```

In `NotebookViewSet` (`backend/notebooks/views.py`), next to the other `@action`s:

```python
    @action(detail=True, methods=['get'], url_path='map')
    def knowledge_map(self, request, pk=None):
        """Concepts, links and the caller's own mastery for this notebook."""
        from .services.knowledge_map import build_map
        return Response(build_map(request.user, self.get_object()))
```

Add `concept_links = models.JSONField(blank=True, default=dict)` to `Notebook` with the comment `# {"hash", "edges": [{"from", "to", "why"}]}: the knowledge map's links, found once per set of concepts.` then run `venv/bin/python manage.py makemigrations notebooks -n notebook_concept_links`.

- [ ] **Step 4:** Run `tests/test_knowledge_map.py`; expected 5 passed. Then the whole Django suite; expected all green. Apply the migration to the dev database: `venv/bin/python manage.py migrate notebooks`.

- [ ] **Step 5: Commit**

```bash
git add backend/notebooks backend/tests/test_knowledge_map.py
git commit -m "feat(map): concepts and the student's own mastery per notebook"
```

---

### Task 6: Finding links, and concept practice

**Files:**
- Modify: `backend/notebooks/services/knowledge_map.py` (`find_links`)
- Modify: `backend/notebooks/views.py` (actions `map_links`, `map_practice`)
- Modify: `backend/tests/conftest.py` (stub `notebooks.services.knowledge_map.get_ai_provider` in the autouse fixture's list)
- Modify: `backend/locale/vi/LC_MESSAGES/django.po` (+ `msgfmt`)
- Test: `backend/tests/test_knowledge_map.py` (append)

**Interfaces:**
- Consumes: `concepts_of`, `concepts_hash`, `clean_links`, `quizzes.services.practice.generate_practice_quiz(user, notebook, label, questions, key)`.
- Produces: `find_links(notebook) -> list[dict]` (raises `LinksUnavailable`); routes `POST .../map/links/` → `{"edges": [...], "edges_status": "ready"}` or 503; `POST .../map/practice/ {"concept": key}` → `{"quiz_id", "source_ids"}` (201/200) or 400/503.

- [ ] **Step 1: Failing tests** (append)

```python
class Reply:
    def __init__(self, data): self.data = data
    def generate_json(self, prompt):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def _links(client, monkeypatch, nb, data):
    monkeypatch.setattr('notebooks.services.knowledge_map.get_ai_provider', lambda: Reply(data))
    return client.post(MAP.format(nb.id) + 'links/')


def test_links_are_cleaned_and_kept(client, monkeypatch, chem):
    nb, src = chem
    res = _links(client, monkeypatch, nb, {'links': [{'before': 1, 'after': 2, 'why': 'Enzymes act on acids'},
                                                     {'before': 2, 'after': 1, 'why': 'loop'},
                                                     {'before': 7, 'after': 1}]})
    assert res.status_code == 200
    assert res.json()['edges'] == [{'from': f'{src.id}:0', 'to': f'{src.id}:1', 'why': 'Enzymes act on acids'}]
    assert client.get(MAP.format(nb.id)).json()['edges_status'] == 'ready'


def test_a_reply_that_is_not_links_gives_no_edges_but_no_error(client, monkeypatch, chem):
    nb, _ = chem
    res = _links(client, monkeypatch, nb, {'nonsense': True})
    assert res.status_code == 200 and res.json()['edges'] == []


def test_a_failed_request_is_503_and_the_map_still_loads(client, monkeypatch, chem):
    nb, _ = chem
    assert _links(client, monkeypatch, nb, RuntimeError('429 quota')).status_code == 503
    assert client.get(MAP.format(nb.id)).json()['edges_status'] == 'missing'


def test_practice_needs_a_concept_with_questions(client, chem):
    nb, src = chem
    res = client.post(MAP.format(nb.id) + 'practice/', {'concept': f'{src.id}:0'}, format='json')
    assert res.status_code == 400
```

- [ ] **Step 2:** Run the file; expected FAIL (404 on `links/`).

- [ ] **Step 3: Implement**

In `knowledge_map.py`:

```python
from django.utils.translation import gettext as _

from ml_pipeline.concept_map import clean_links
from ml_pipeline.language import detect_language, language_name
from notebooks.services.ai_provider import get_ai_provider
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose


class LinksUnavailable(Exception):
    pass


def find_links(notebook) -> list[dict]:
    """One request: which concepts must be understood before which."""
    concepts = concepts_of(notebook)
    if len(concepts) < 2:
        return []
    listed = '\n'.join(f'{c["index"]}. {c["label"]}: {c["point"]}' for c in concepts)
    lang = language_name(detect_language(listed))
    prompt = f"""These are the concepts of one subject a student is studying. Say which must be
understood before which: a pair means the second concept cannot be understood without the
first. Only clear, direct dependencies; at most 3 per concept; none for unrelated concepts.
For each pair give one short reason in {lang}.

Concepts:
{listed}

{WRITING_STYLE}

Return ONLY valid JSON: {{"links": [{{"before": 1, "after": 2, "why": "..."}}]}}"""
    try:
        data = get_ai_provider().generate_json(prompt)
    except Exception as exc:  # noqa: BLE001
        raise LinksUnavailable(_('The links between concepts could not be found just now. Try again later.')) from exc
    raw = data.get('links') if isinstance(data, dict) else None
    edges = [{'from': concepts[a]['key'], 'to': concepts[b]['key'], 'why': tidy_prose(why)}
             for a, b, why in clean_links(raw or [], len(concepts))]
    notebook.concept_links = {'hash': concepts_hash(concepts), 'edges': edges}
    notebook.save(update_fields=['concept_links'])
    return edges
```

In `NotebookViewSet`:

```python
    @action(detail=True, methods=['post'], url_path='map/links', throttle_classes=[GenerationRateThrottle])
    def map_links(self, request, pk=None):
        """Find the links between this notebook's concepts (one model request)."""
        from .services.knowledge_map import LinksUnavailable, find_links
        try:
            edges = find_links(self.get_object())
        except LinksUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        return Response({'edges': edges, 'edges_status': 'ready'})

    @action(detail=True, methods=['post'], url_path='map/practice', throttle_classes=[GenerationRateThrottle])
    def map_practice(self, request, pk=None):
        """Five fresh questions on one concept, from its questions' passages."""
        import hashlib
        from quizzes.models import Question
        from quizzes.services.practice import PracticeUnavailable, generate_practice_quiz
        from .services.knowledge_map import build_map
        notebook = self.get_object()
        concept = next((c for c in build_map(request.user, notebook)['concepts']
                        if c['key'] == request.data.get('concept')), None)
        action_ = (concept or {}).get('action') or {}
        if concept is None or action_.get('kind') != 'practice':
            return Response({'detail': _('This concept has no questions to practise from yet.')}, status=400)
        questions = list(Question.objects.filter(id__in=action_['question_ids']).select_related('source'))
        key = hashlib.sha1(f'map:{notebook.id}:{concept["key"]}'.encode()).hexdigest()[:12]
        existing = Quiz.objects.filter(user=request.user, is_published=True, practice_key=key).first()
        try:
            quiz = existing or generate_practice_quiz(request.user, notebook, concept['label'], questions, key=key)
        except PracticeUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        return Response({'quiz_id': quiz.id, 'source_ids': sorted(quiz.sources.values_list('id', flat=True))},
                        status=200 if existing else 201)
```

(Import `Quiz` from `quizzes.models` and `_` from `django.utils.translation` at the top of `views.py` if not already imported.) Add `'notebooks.services.knowledge_map.get_ai_provider'` to the stub list in `backend/tests/conftest.py`. Add the two msgids with Vietnamese to `django.po`: "Chưa tìm được mối liên hệ giữa các khái niệm lúc này. Thử lại sau." and "Khái niệm này chưa có câu hỏi để luyện." Then run `msgfmt -c -o locale/vi/LC_MESSAGES/django.mo locale/vi/LC_MESSAGES/django.po`.

- [ ] **Step 4:** Run the file (9 passed), then the full Django suite.

- [ ] **Step 5: Commit**

```bash
git add backend/notebooks backend/tests backend/locale/vi/LC_MESSAGES/django.po
git commit -m "feat(map): find links between concepts and practise one concept"
```

---

### Task 7: Deterministic layout

**Files:**
- Create: `lib/map-layout.ts`
- Test: `lib/map-layout.test.ts`

**Interfaces:**
- Produces: `layoutMap(keys: string[], edges: {from: string; to: string}[], size?: {w: number; h: number}) -> Record<string, {x: number; y: number}>`; constants `CARD_W = 208`, `CARD_H = 112`.

- [ ] **Step 1: Failing tests**

```ts
// Run with: pnpm test  (node --test; Node strips the types itself)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { CARD_H, CARD_W, layoutMap } from './map-layout.ts'

const overlap = (a: { x: number; y: number }, b: { x: number; y: number }) =>
  Math.abs(a.x - b.x) < CARD_W && Math.abs(a.y - b.y) < CARD_H

test('the same data always gives the same picture', () => {
  const keys = ['a', 'b', 'c', 'd']
  const edges = [{ from: 'a', to: 'c' }, { from: 'b', to: 'c' }, { from: 'c', to: 'd' }]
  assert.deepEqual(layoutMap(keys, edges), layoutMap(keys, edges))
})

test('a prerequisite sits left of what depends on it', () => {
  const pos = layoutMap(['a', 'b', 'c'], [{ from: 'a', to: 'b' }, { from: 'b', to: 'c' }])
  assert.ok(pos.a.x < pos.b.x && pos.b.x < pos.c.x)
})

test('no two cards overlap, even with many concepts and no links', () => {
  const keys = Array.from({ length: 45 }, (_, i) => `k${i}`)
  const pos = layoutMap(keys, [])
  for (let i = 0; i < keys.length; i++)
    for (let j = i + 1; j < keys.length; j++) assert.ok(!overlap(pos[keys[i]], pos[keys[j]]), `${keys[i]} ${keys[j]}`)
  const rows = new Set(keys.map((k) => pos[k].y)).size
  assert.ok(rows <= 14, 'wraps into columns instead of one tall column')
})

test('links to unknown cards are ignored', () => {
  const pos = layoutMap(['a'], [{ from: 'x', to: 'a' }])
  assert.deepEqual(Object.keys(pos), ['a'])
})
```

- [ ] **Step 2:** Run `node --test lib/map-layout.test.ts`; expected FAIL (module not found).

- [ ] **Step 3: Implement**

```ts
/** Where each concept card sits on the knowledge map. Deterministic, so the
 *  map looks the same every visit: prerequisites to the left, what depends
 *  on them further right, each layer staggered so the whole reads as a
 *  network rather than columns. A layer taller than MAX_ROWS wraps into
 *  extra columns, so forty unlinked concepts do not make one tall strip. */
export const CARD_W = 208
export const CARD_H = 112
const GAP_X = 96
const GAP_Y = 36
const MAX_ROWS = 6

export function layoutMap(
  keys: string[],
  edges: { from: string; to: string }[],
): Record<string, { x: number; y: number }> {
  const known = new Set(keys)
  const links = edges.filter((e) => known.has(e.from) && known.has(e.to) && e.from !== e.to)
  const layer: Record<string, number> = {}
  const depth = (k: string, seen: Set<string>): number => {
    if (layer[k] !== undefined) return layer[k]
    if (seen.has(k)) return 0
    seen.add(k)
    const before = links.filter((e) => e.to === k).map((e) => depth(e.from, seen) + 1)
    layer[k] = before.length ? Math.max(...before) : 0
    return layer[k]
  }
  keys.forEach((k) => depth(k, new Set()))

  // Order within a layer by where its prerequisites sit, so arrows cross less.
  const layers: string[][] = []
  for (const k of keys) (layers[layer[k]] ??= []).push(k)
  const rowOf: Record<string, number> = {}
  layers.forEach((ks, li) => {
    if (li > 0) {
      const bary = (k: string) => {
        const ps = links.filter((e) => e.to === k).map((e) => rowOf[e.from] ?? 0)
        return ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : Number.MAX_SAFE_INTEGER
      }
      ks.sort((a, b) => bary(a) - bary(b) || keys.indexOf(a) - keys.indexOf(b))
    }
    ks.forEach((k, i) => (rowOf[k] = i))
  })

  const pos: Record<string, { x: number; y: number }> = {}
  let column = 0
  layers.forEach((ks) => {
    if (!ks) return
    for (let start = 0; start < ks.length; start += MAX_ROWS) {
      const chunk = ks.slice(start, start + MAX_ROWS)
      const stagger = column % 2 ? (CARD_H + GAP_Y) / 2 : 0
      chunk.forEach((k, i) => (pos[k] = { x: column * (CARD_W + GAP_X), y: stagger + i * (CARD_H + GAP_Y) }))
      column += 1
    }
  })
  return pos
}
```

- [ ] **Step 4:** Run `pnpm test`; expected all pass (17 + 4).

- [ ] **Step 5: Commit**

```bash
git add lib/map-layout.ts lib/map-layout.test.ts
git commit -m "feat(map): deterministic layout for concept cards"
```

---

### Task 8: The map in the notebook page

**Files:**
- Modify: `package.json`, `pnpm-lock.yaml` (`pnpm add @xyflow/react`)
- Modify: `lib/api.ts` (types + `notebooksAPI.getMap`, `findMapLinks`, `practiseConcept`)
- Create: `components/knowledge-map.tsx` (canvas, card node, detail panel, empty and pending states)
- Modify: `components/notebook-workspace.tsx` (Tài liệu · Bản đồ switch, `?view=map`)
- Modify: `app/dashboard/analytics/page.tsx` ("Xem bản đồ" link on each "Theo sổ tay" row)
- Modify: `messages/vi.json`, `messages/en.json` (namespace `map`)

**Interfaces:**
- Consumes: `/map/`, `/map/links/`, `/map/practice/`; `layoutMap`, `CARD_W`, `CARD_H`.
- Produces: `<KnowledgeMap notebookId={number} />`.

- [ ] **Step 1: API types** (append to `lib/api.ts`; add the three calls inside `notebooksAPI`)

```ts
export type ConceptState = 'strong' | 'shaky' | 'weak' | 'not_studied'
export type ConceptAction =
  | { kind: 'cards'; card_ids: number[] }
  | { kind: 'exercise'; exercise_id: number }
  | { kind: 'practice'; question_ids: number[] }
export type MapConcept = {
  key: string; label: string; point: string; source_ids: number[]; importance: 'core' | 'supporting'
  state: ConceptState
  understanding: { p: number; correct: number; total: number } | null
  memory: { p: number; remembered: number; total: number } | null
  events: number; action: ConceptAction | null; first: string | null
}
export type KnowledgeMapData = {
  concepts: MapConcept[]; edges: { from: string; to: string; why: string }[]
  edges_status: 'ready' | 'missing' | 'none'
  missing_key_points: { source_id: number; title: string }[]; unattached: number
}
```

```ts
  getMap: (id: number) => api.get<KnowledgeMapData>(`/notebooks/notebooks/${id}/map/`),
  findMapLinks: (id: number) => api.post<{ edges: KnowledgeMapData['edges'] }>(`/notebooks/notebooks/${id}/map/links/`),
  practiseConcept: (id: number, concept: string) =>
    api.post<{ quiz_id: number; source_ids: number[] }>(`/notebooks/notebooks/${id}/map/practice/`, { concept }),
```

- [ ] **Step 2: Messages** (`map` namespace, both files; Vietnamese shown, English mirrors it)

```json
"map": {
  "documents": "Tài liệu", "map": "Bản đồ",
  "lead": "Mỗi khung là một ý chính của sổ tay. Màu theo phần bạn yếu hơn: hiểu (làm bài) hay nhớ (ôn thẻ). Mũi tên: cần hiểu cái này trước.",
  "state_strong": "Nắm chắc", "state_shaky": "Chưa vững", "state_weak": "Yếu", "state_not_studied": "Chưa học",
  "once": "mới luyện 1 lần",
  "memoryLine": "nhớ {remembered}/{total} thẻ", "understandingLine": "đúng {correct}/{total} câu",
  "notStudiedLine": "chưa luyện",
  "understanding": "Hiểu", "memory": "Nhớ",
  "adviceMemory": "Phần hiểu đã ổn hơn, chỉ cần nhắc lại thẻ.",
  "adviceUnderstanding": "Bạn nhớ thẻ nhưng làm bài còn sai: cần luyện vận dụng.",
  "adviceStart": "Chưa luyện khái niệm này lần nào.",
  "adviceStrong": "Đang vững. Ôn theo lịch là đủ.",
  "firstNeeds": "{label} ({state}) là nền của khái niệm này, nên ôn trước.",
  "goFirst": "Xem {label}",
  "actionCards": "Ôn {count, plural, other {# thẻ}}", "actionExercise": "Làm bài vận dụng", "actionPractice": "Luyện 5 câu",
  "practising": "Đang soạn câu hỏi…",
  "needs": "Cần hiểu trước", "reason": "Vì sao",
  "recenter": "Về giữa", "onlyWeak": "Chỉ hiện chỗ yếu", "showAll": "Hiện tất cả",
  "linksPending": "Đang tìm mối liên hệ giữa các khái niệm…",
  "linksFailed": "Chưa tìm được mối liên hệ, thử lại sau.", "retry": "Thử lại",
  "noConcepts": "Bản đồ được dựng từ ý chính của tài liệu. Rút ý chính cho một tài liệu để bắt đầu.",
  "missingKeyPoints": "Chưa có ý chính: {titles}",
  "readKeyPoints": "Rút ý chính",
  "close": "Đóng",
  "viewMap": "Xem bản đồ",
  "listLabel": "Các khái niệm trong bản đồ"
}
```

Run `.venv/bin/python -m pytest tests/test_messages_parity.py -q`; expected pass.

- [ ] **Step 3: `components/knowledge-map.tsx`** — build it with these parts, all in the existing paper style:

1. `useSWR(['/map', notebookId], () => notebooksAPI.getMap(notebookId))`. When `edges_status === 'missing'`, call `findMapLinks` once (a ref guards against repeats), then `mutate()`; on failure keep a `linksFailed` flag and show the retry line.
2. Nodes: `layoutMap(concepts.map(c => c.key), edges)` → React Flow `nodes` with `type: 'concept'`, `draggable: false`, `selectable: true`; edges `type: 'default'` (bezier), `markerEnd: { type: MarkerType.ArrowClosed }`, stroke `#94a3b8`, the selected card's incoming edges stroke `#2563eb` and `animated: false`.
3. `ConceptNode`: a `rounded-xl border bg-white px-3 py-2.5 shadow-sheet` card of `CARD_W` × auto (min `CARD_H`), with target `Handle` on the left and source `Handle` on the right (`isConnectable={false}`, `className="!opacity-0"`); a state dot, the label (`font-medium`, two lines max), a 5px mastery bar (emerald/amber/red/slate by state, width = weaker signal × 100), a mono line with the numbers (`memoryLine` · `understandingLine`, or `notStudiedLine`). Weak cards have a pale red border; `events === 1` uses `border-dashed` and the `once` label. Selected: `ring-[3px] ring-mode/30 border-mode`. Faded (`onlyWeak` and state strong): `opacity-40`. `transition-[opacity,box-shadow] duration-200 motion-reduce:transition-none`.
4. Canvas: `<ReactFlow fitView fitViewOptions={{ padding: 0.15 }} minZoom={0.3} maxZoom={1.6} nodesConnectable={false} proOptions={{ hideAttribution: true }}>` with `<Background variant={BackgroundVariant.Lines} gap={22} color="#eef2f7" />`; height `h-[70dvh] min-h-[420px]`. Toolbar above: "Về giữa" (`useReactFlow().fitView()`), "Chỉ hiện chỗ yếu" toggle.
5. Detail panel for the selected concept: desktop a right column (`md:grid-cols-[minmax(0,1fr)_20rem]`), phone a bottom sheet (`fixed inset-x-0 bottom-0 z-40 rounded-t-2xl` with a close button, `max-h-[60dvh] overflow-y-auto`). Contents: label, state word, the two signals (`Hiểu: đúng 4/5 câu`, `Nhớ: nhớ 2/6 thẻ`, the weaker marked), the advice line, the `first` prerequisite line with a "Xem …" button that selects it, the action button (cards → `Link` to `/dashboard/flashcards?cards=…`; exercise → `/dashboard/practice/{id}`; practice → `practiseConcept` then `router.push('/dashboard/quizzes?source=…&quiz=…')`), and for each incoming edge its `why`.
6. Keyboard and screen readers: a visually hidden `<ul aria-label={t('listLabel')}>` listing each concept with its state and numbers as buttons that select it; Escape closes the panel.
7. Empty state (no concepts): `noConcepts` plus, for each `missing_key_points` entry, a "Rút ý chính" button calling `notebooksAPI.readSource(source_id)` then `mutate()`. When some documents lack key points, a one-line note `missingKeyPoints` above the canvas.
8. `import '@xyflow/react/dist/style.css'` at the top of the component.

- [ ] **Step 4: Switch in the notebook page** — in `components/notebook-workspace.tsx` read `const view = searchParams.get('view') === 'map' ? 'map' : 'documents'`; above the documents heading add a two-button segmented control (`role="tablist"`, buttons `role="tab" aria-selected`) that calls `router.replace` with `?view=map` or without it (keeping `source`); render `<KnowledgeMap notebookId={notebookId} />` in place of the documents section when `view === 'map'`.

- [ ] **Step 5: Progress link** — in `app/dashboard/analytics/page.tsx`, under each "Theo sổ tay" row's numbers, add `<Link href={`/dashboard/notebooks/${n.notebook_id}?view=map`}>{mapT('viewMap')} →</Link>` outside the row's main link (the row is already a link; put this one beside the review button so links do not nest).

- [ ] **Step 6: Check** — `npx tsc --noEmit -p .`; `pnpm test`; `pnpm lint` (no new warnings in the touched files); parity test.

- [ ] **Step 7: Commit**

```bash
git add package.json pnpm-lock.yaml lib/api.ts components/knowledge-map.tsx components/notebook-workspace.tsx app/dashboard/analytics/page.tsx messages/vi.json messages/en.json
git commit -m "feat(map): knowledge map view in the notebook page"
```

---

### Task 9: Notebook 10, parts 2–3, and the visual check

**Files:**
- Create: `backend/notebooks/management/commands/dump_concept_items.py` (writes concepts and items of one account to `ml_pipeline/outputs/concept_items.json`, ignored)
- Create: `datasets/handmade/concept_attachment.json` (about 60 items: `{"item": "card:12", "text": "...", "concept": "<key> | null"}`, labelled by reading each item against the concepts)
- Modify: `ml_pipeline/notebooks/10_knowledge_map.ipynb` (append), the scratchpad builder script
- Modify: `ml_pipeline/concept_map.py` (thresholds only if the notebook shows a better value)

- [ ] **Step 1: Dump** — `venv/bin/python manage.py dump_concept_items --email studyflow.demo@gmail.com`: for each notebook, `concepts_of(nb)` and `_items(user, nb)[3]`, written with the notebook id. Read-only.

- [ ] **Step 2: Label** about 60 items across the three demo notebooks by hand into `datasets/handmade/concept_attachment.json`; include items that belong to no concept (`null`).

- [ ] **Step 3: Notebook cells** (append): load both files; for `ATTACH_THRESHOLD` in 0.05…0.30 report accuracy (exact concept, `null` counting as a label) and coverage; pick the best and state it; same for `MERGE_THRESHOLD` over the demo key points, listing the merged pairs at the chosen value for a reader to judge; then list the links found for the demo notebooks (from `Notebook.concept_links`, dumped by the command) and count edges per notebook. Markdown: limits (one account, labels by one person).

- [ ] **Step 4:** If the chosen thresholds differ from the constants, update `ml_pipeline/concept_map.py` and re-run `tests/test_concept_map.py`.

- [ ] **Step 5: Visual check** with the read-only bridge (`BRIDGE_EMAIL=studyflow.demo@gmail.com`; links are a POST, so first call `find_links` for the three demo notebooks from a Django shell). Screenshot `/dashboard/notebooks/<id>?view=map` at 1280×900 and 390×844, with a concept selected; fix overlaps, clipped text, contrast, panel behaviour; `pkill -f readonly_bridge.py` afterwards.

- [ ] **Step 6: Full suites** (ML, Django, frontend, tsc, lint), then commit:

```bash
git add backend/notebooks/management/commands/dump_concept_items.py datasets/handmade/concept_attachment.json ml_pipeline/notebooks/10_knowledge_map.ipynb ml_pipeline/concept_map.py datasets/README.md
git commit -m "feat(ml): check concept attachment and links on the demo account"
```

- [ ] **Step 7:** Push and merge as usual (`feat/group-chat` → `feat/ml-dataset-registry` through a worktree in the scratchpad).
