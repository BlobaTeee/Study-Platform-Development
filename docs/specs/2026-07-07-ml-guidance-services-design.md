# ML Guidance Services — Design Spec

**Status:** Approved (brainstorming) — ready for implementation planning
**Date:** 2026-07-07
**Depends on:** `2026-07-03-ml-foundation-design.md` (processed parquet + topic hierarchy)

## 1. Goal

Implement the two **Guidance** modules under `ml_pipeline/services/` that the Django
adapter ([`backend/ml/adapter.py`](../../../backend/ml/adapter.py)) already imports but
that do not yet exist:

- `ml_pipeline/services/recommendation_engine.py` → `RecommendationEngine`
- `ml_pipeline/services/learning_path.py` → `LearningPathEngine`

plus one shared internal module they both build on:

- `ml_pipeline/services/topic_index.py` → `TopicIndex`

When these exist, the analytics page's **Study Recommendations** and **Adaptive Learning
Path** panels go live immediately — the REST endpoints and frontend already call them
(today they return `unavailable`/`[]` because the import throws).

**Out of scope (own later specs):** the Generation subsystem (`FlashcardGenerator`,
`QuizGenerator`), and platform-feedback retraining. See §10.

## 2. Context & constraints (the data realities that shape this design)

These are verified facts about the running system, not assumptions:

1. **Taxonomy gap.** Student flashcards are tagged `source:N` (which notebook source);
   0 of the current cards have the Django `topic` FK set. The ML **topic hierarchy** is a
   *separate* curriculum taxonomy (157 `subject/topic/subtopic` triples from the AI
   Flashcards training data). Nothing currently links a student's own content to it.
2. **Cold start is the default.** There are currently 0 completed quiz attempts and 0
   flashcards with correct/incorrect history. A "performance profile" is empty for
   essentially every user. **The engines must treat empty data as the normal case** and
   still return something useful; they get better as usage accumulates.
3. **Difficulty comes from data, not a predictor.** The AI Flashcards dataset carries a
   per-row `difficulty` label. We **aggregate** those labels per subtopic. We do **not**
   build a difficulty predictor (the foundation EDA found difficulty statistically
   independent of text features — prediction would be no better than guessing).
4. **Classical + local only.** No LLM, no network, no external API. Pure local parquet +
   scikit-learn TF-IDF. This is the core "built to last" property: nothing to rate-limit,
   expire, or depend on a third party for.
5. **`ml_pipeline` stays framework-free.** No Django imports inside `ml_pipeline`. Methods
   accept duck-typed record iterables (read `.correct_count`, `.is_correct`, …) so they
   work with the Django querysets the adapter passes *and* with plain test fixtures.

## 3. Integration contract (fixed — do not change signatures)

The adapter already dictates these method signatures. The frontend `Recommendation` /
`PathStep` TypeScript types dictate the output dict keys.

### RecommendationEngine
```python
build_performance_profile(flashcards, quiz_attempts) -> dict      # "performance_by_topic"
recommend_from_text(study_text: str, performance_by_topic: dict, n: int) -> list[dict]
```
Each recommendation dict:
```python
{"subject": str, "topic": str, "subtopic": str, "label": str,
 "priority": float, "recommended_difficulty": "easy|medium|hard", "reason": str}
```

### LearningPathEngine
```python
estimate_mastery_from_performance(profile) -> set[str]            # mastered subtopics
get_learning_path(subject: str | None, mastered_subtopics, limit: int) -> list[dict]
```
Each path step dict:
```python
{"step": int, "subject": str, "topic": str, "subtopic": str,
 "difficulty": "easy|medium|hard", "status": "mastered|current|upcoming"}
```

## 4. Architecture & module layout

```
ml_pipeline/services/
├── topic_index.py            # shared internal: parquet load + TF-IDF + difficulty lookup
├── recommendation_engine.py  # RecommendationEngine (adapter-facing)
└── learning_path.py          # LearningPathEngine   (adapter-facing)
```

Each unit has one clear purpose, a well-defined interface, and is independently testable.
The engines hold only their logic; all data loading/indexing lives in `TopicIndex`.

## 5. Component design

### 5.1 TopicIndex (`topic_index.py`)

A lazily-built, **process-memoized singleton**. Built once; never re-read per request.

Responsibilities:
- Load `topic_hierarchy.parquet` (`subject, topic, subtopic, count`).
- Aggregate a `difficulty` per subtopic from `flashcards.parquet`'s `difficulty` column
  (majority vote; `"medium"` when absent or the column is missing).
- Build a TF-IDF matrix over each subtopic's text: `"subject topic subtopic"` enriched
  with a sample of that subtopic's flashcard `question` text (richer than three words).
- Public methods:
  - `search(text: str, n: int) -> list[Row]` — TF-IDF cosine ranked subtopics (desc,
    tie-break by subtopic name).
  - `rows_for_subject(subject: str) -> list[Row]`
  - `subjects() -> list[str]`
  - `top_by_coverage(n: int) -> list[Row]` — cold-start default ordering.
  - `difficulty_for(subject, topic, subtopic) -> str`
- Accessor `get_topic_index()` returns the memoized instance. Raises if parquet is missing
  (→ surfaces as 503 through the adapter; see §7).

`Row` is a small dataclass: `subject, topic, subtopic, count, difficulty`.

### 5.2 RecommendationEngine (`recommendation_engine.py`)

**`build_performance_profile(flashcards, quiz_attempts) -> dict`**
- Flashcards: per-card accuracy `correct_count / (correct_count + incorrect_count)`,
  grouped by the card's `topic` name when present.
- Quizzes: per-attempt `score` and/or per-`Answer` `is_correct`, grouped by the quiz's
  `topic` name.
- Returns `{"by_topic": {topic_name: {"n": int, "accuracy": float}}, "overall_accuracy": float | None}`.
- Sparse/empty is expected and valid.

**`recommend_from_text(study_text, performance_by_topic, n) -> list[dict]`**
1. **Warm path** (non-empty `study_text`): `TopicIndex.search(study_text, n * K)` for
   candidate subtopics with a relevance score.
2. **Cold path** (empty `study_text`): `TopicIndex.top_by_coverage(n * K)`; relevance =
   normalized coverage.
3. `priority = relevance * weakness_weight`. The weight is found by looking up the
   candidate row's `topic` name (case-insensitive exact match) in
   `performance_by_topic["by_topic"]`: accuracy `< WEAK_ACCURACY_THRESHOLD` → `WEAK_WEIGHT`
   (`> 1`); accuracy strong → `STRONG_WEIGHT` (`< 1`); **no matching key → exactly `1.0`**
   (the common cold case).
4. Sort by `priority` desc (tie-break subtopic name); take `n`.
5. Attach `recommended_difficulty = TopicIndex.difficulty_for(...)`, a `label`
   (`f"{topic} · {subtopic}"`), and a human `reason`:
   - warm + weak: `"You've been scoring lower on {topic}"`
   - warm: `"Closely matches your study notes"`
   - cold: `"Foundational topic in {subject}"`
6. Return `[]` (never raise) if the index yields no candidates.

Named constants at module top: `CANDIDATE_MULTIPLIER K`, `WEAK_ACCURACY_THRESHOLD`,
`WEAK_WEIGHT`, `STRONG_WEIGHT`.

### 5.3 LearningPathEngine (`learning_path.py`)

**`estimate_mastery_from_performance(profile) -> set[str]`**
- A topic/subtopic is *mastered* when profile accuracy `>= MASTERY_THRESHOLD (0.8)` with
  `n >= MIN_MASTERY_POINTS (2)` (guards against "1/1 = mastered").
- Matching is best-effort by case-insensitive exact name: a `by_topic` key equal to a
  hierarchy `topic` or `subtopic` name marks that subtopic mastered. Cold profile → empty
  set. (This is intentionally loose in v1; §2.1's taxonomy gap means most profiles won't
  match, which is acceptable — mastery simply stays empty until linkage improves.)

**`get_learning_path(subject, mastered_subtopics, limit) -> list[dict]`**
1. `rows = TopicIndex.rows_for_subject(subject)`; if `subject is None`, default to the
   highest-coverage subject so the panel is never empty.
2. **Order:** difficulty `easy → medium → hard`, then `count` (coverage) desc within each.
3. **Status:** subtopic in `mastered_subtopics` → `"mastered"`; the first non-mastered →
   `"current"`; the rest → `"upcoming"`.
4. Number steps `1..limit`; attach `difficulty` from `TopicIndex`.
5. Return `[]` if the index can't load or the subject has no rows.

Named constants: `MASTERY_THRESHOLD = 0.8`, `MIN_MASTERY_POINTS = 2`,
`DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}`.

## 6. Data flow

```
Analytics page (studyContext, subject)
  → GET /api/analytics/sessions/{recommendations,learning_path}/
    → ml.adapter.get_study_recommendations / get_learning_path
      → RecommendationEngine / LearningPathEngine
        → TopicIndex (memoized: topic_hierarchy.parquet + flashcards.parquet)
      ← list[dict] matching the frontend types
```

## 7. Error handling & durability

- **Load once, cache:** `TopicIndex` memoized per process; TF-IDF fit happens once.
- **Two-tier failures:**
  - *Cold / no match / empty profile* → return `[]` / empty profile → endpoint 200, empty
    → frontend's "No recommendations yet…" state. Normal.
  - *Genuinely broken* (parquet missing/corrupt) → `TopicIndex` raises → adapter's
    existing `try/except` → **503 "unavailable"**. Honest misconfiguration signal.
- **Determinism:** stable sorts with explicit tie-breakers; any sampling seeded with
  `config.RANDOM_SEED`.
- **Tolerant loading:** missing `difficulty` column → `"medium"`; unexpected columns
  ignored — survives foundation data evolution.
- **Tunables** live as named constants at module tops, not scattered magic numbers.

## 8. Testing (TDD, mirroring the foundation)

Unit tests with tiny fixtures (small hierarchy + flashcards DataFrames; fake querysets as
namedtuples — no DB):
- `TopicIndex`: `search` relevance; difficulty majority-vote; missing-difficulty → medium;
  `top_by_coverage` ordering; `rows_for_subject`.
- `RecommendationEngine`: profile accuracy math; warm-path ranks the relevant subtopic
  top; cold-path returns coverage order; weakness boost changes order; `[]` on empty index;
  exact output keys + difficulty ∈ {easy,medium,hard}.
- `LearningPathEngine`: mastery threshold + min-points; difficulty-then-coverage order;
  status assignment (mastered/current/upcoming); default subject when `None`; `limit`
  respected; exact output keys.
- **Real-data integration test:** build engines against actual processed parquet; assert
  `"calculus continuity"` surfaces `Calculus` subtopics and every dict has the right keys.
- **Adapter contract check:** `from ml.adapter import get_study_recommendations` /
  `get_learning_path` import + call path works (Django-dependent; noted like foundation
  Task 12).

## 9. Acceptance criteria

1. The three modules exist; `ml_pipeline/services/__init__.py` exposes the engines.
2. `RecommendationEngine` and `LearningPathEngine` satisfy the §3 signatures and output
   shapes exactly.
3. Cold start (no study text, empty profile) returns non-empty, sensible results.
4. Warm path: a query returns relevance-ranked subtopics; weakness weighting affects order.
5. All difficulty values ∈ {easy, medium, hard}; path statuses ∈ {mastered, current,
   upcoming}.
6. Engines return `[]` on empty/cold and only raise on genuine load failure.
7. Full test suite passes, including the real-data integration test.
8. `USE_ML_PRIMARY` is irrelevant here — these endpoints are ungated; building the modules
   makes the analytics panels live.

## 10. Out of scope / future

- **Generation subsystem** (`FlashcardGenerator`, `QuizGenerator` + AnswerScorer wiring) —
  its own spec/plan/build cycle.
- **Approach B — canonical hierarchy enrichment:** bake `difficulty` (and a
  `foundational_rank`) into `topic_hierarchy.parquet` via the foundation's
  `build_topic_hierarchy`, so the engines read one canonical topic table instead of
  aggregating difficulty at runtime. A clean future refactor once guidance has proven out.
- **Taxonomy linkage:** classify student content into hierarchy subtopics (closing the
  §2.1 gap) so performance weighting becomes strong rather than best-effort.
- **Platform-feedback retraining** (`retrain_all` using `platform_cards`).
