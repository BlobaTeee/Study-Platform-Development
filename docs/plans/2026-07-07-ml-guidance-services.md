# ML Guidance Services Implementation Plan

**Goal:** Implement the `RecommendationEngine` and `LearningPathEngine` (plus a shared `TopicIndex`) under `ml_pipeline/services/` so the analytics page's Study Recommendations and Adaptive Learning Path panels go live.

**Architecture:** A shared, process-memoized `TopicIndex` loads the processed parquet once, builds a TF-IDF index over the topic hierarchy, and aggregates a difficulty label per subtopic from the flashcards dataset. Two thin engine classes hold only their logic and call into `TopicIndex`. Everything is classical (scikit-learn TF-IDF), local, and framework-free.

**Tech Stack:** Python 3.11, pandas, scikit-learn (TfidfVectorizer), pyarrow (parquet), pytest.

## Global Constraints

- `ml_pipeline` stays **Django-free**. Engine methods accept duck-typed record iterables (read `.correct_count`, `.incorrect_count`, `.topic.name`, `.score`, `.quiz.topic.name`), so they work with Django querysets *and* plain test fixtures. Verbatim from spec §2.5.
- **Classical + local only** — no LLM, no network, no external API. Spec §2.4.
- **Signatures are fixed** by `backend/ml/adapter.py` (spec §3); **output dict keys are fixed** by the frontend `Recommendation` / `PathStep` types. Do not change them.
- Recommendation dict keys: `subject, topic, subtopic, label, priority, recommended_difficulty, reason`. Path step keys: `step, subject, topic, subtopic, difficulty, status`.
- Engines **return `[]` / empty profile on cold/empty inputs and raise only on genuine load failure** (missing/corrupt parquet). Spec §7.
- Difficulty values ∈ `{easy, medium, hard}`; path status ∈ `{mastered, current, upcoming}`.
- `RANDOM_SEED = 42`; reuse `config.TFIDF_MAX_FEATURES`, `config.TFIDF_NGRAM` for the vectorizer.
- All commands use the repo venv: `.venv/bin/python` / `.venv/bin/pytest`.
- Tunables live as named constants at module tops — no scattered magic numbers.

---

## Task 1: TopicIndex (shared spine) + fixtures

**Files:**
- Create: `ml_pipeline/services/topic_index.py`
- Modify: `tests/conftest.py` (add shared guidance fixtures)
- Test: `tests/test_topic_index.py`

**Interfaces:**
- Consumes: `ml_pipeline.config` (`TFIDF_MAX_FEATURES`, `TFIDF_NGRAM`), `ml_pipeline.dataset_loader.load_processed`
- Produces:
  - `@dataclass(frozen=True) TopicRow(subject: str, topic: str, subtopic: str, count: int, difficulty: str)`
  - `class TopicIndex`:
    - `TopicIndex.from_frames(hierarchy_df, flashcards_df) -> TopicIndex`
    - `TopicIndex.load() -> TopicIndex`
    - `.search(text: str, n: int) -> list[tuple[TopicRow, float]]` (desc score, tie-break subtopic; only score>0)
    - `.top_by_coverage(n: int) -> list[TopicRow]` (desc count, tie-break subtopic)
    - `.rows_for_subject(subject: str) -> list[TopicRow]`
    - `.subjects() -> list[str]` (sorted)
    - `.default_subject() -> str | None` (highest total coverage)
    - `.difficulty_for(subject, topic, subtopic) -> str`
  - `get_topic_index() -> TopicIndex` (memoized singleton)

- [ ] **Step 1: Add shared fixtures to `tests/conftest.py`** (append)

```python
@pytest.fixture
def guidance_hierarchy_df():
    """Tiny topic hierarchy: 2 subjects, 4 subtopics with coverage counts."""
    import pandas as pd
    return pd.DataFrame([
        {"subject": "Mathematics", "topic": "Calculus", "subtopic": "Continuity", "count": 30},
        {"subject": "Mathematics", "topic": "Calculus", "subtopic": "Limits", "count": 50},
        {"subject": "Mathematics", "topic": "Algebra", "subtopic": "Polynomials", "count": 20},
        {"subject": "Physics", "topic": "Mechanics", "subtopic": "Kinematics", "count": 40},
    ])


@pytest.fixture
def guidance_flashcards_df():
    """Tiny flashcards frame with difficulty labels + question text per subtopic."""
    import pandas as pd
    return pd.DataFrame([
        {"subject": "Mathematics", "topic": "Calculus", "subtopic": "Continuity",
         "difficulty": "hard", "question": "What is continuity of a function?"},
        {"subject": "Mathematics", "topic": "Calculus", "subtopic": "Continuity",
         "difficulty": "hard", "question": "Define a continuous limit at a point."},
        {"subject": "Mathematics", "topic": "Calculus", "subtopic": "Limits",
         "difficulty": "easy", "question": "What is the limit of a sequence?"},
        {"subject": "Mathematics", "topic": "Algebra", "subtopic": "Polynomials",
         "difficulty": "medium", "question": "What is the degree of a polynomial?"},
        {"subject": "Physics", "topic": "Mechanics", "subtopic": "Kinematics",
         "difficulty": "medium", "question": "What is velocity in kinematics?"},
    ])
```

- [ ] **Step 2: Write the failing test** `tests/test_topic_index.py`

```python
from ml_pipeline.services.topic_index import TopicIndex, TopicRow


def test_from_frames_builds_rows_with_difficulty(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    rows = idx.rows_for_subject("Mathematics")
    assert {r.subtopic for r in rows} == {"Continuity", "Limits", "Polynomials"}
    # difficulty aggregated from flashcards (majority vote)
    assert idx.difficulty_for("Mathematics", "Calculus", "Continuity") == "hard"
    assert idx.difficulty_for("Mathematics", "Calculus", "Limits") == "easy"


def test_missing_difficulty_defaults_to_medium(guidance_hierarchy_df):
    import pandas as pd
    idx = TopicIndex.from_frames(guidance_hierarchy_df, pd.DataFrame())
    assert idx.difficulty_for("Physics", "Mechanics", "Kinematics") == "medium"


def test_search_ranks_relevant_subtopic_first(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    hits = idx.search("continuity of a function", n=3)
    assert hits, "expected at least one hit"
    top_row, top_score = hits[0]
    assert top_row.subtopic == "Continuity"
    assert top_score > 0


def test_search_empty_text_returns_empty(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    assert idx.search("", n=5) == []


def test_top_by_coverage_orders_by_count(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    top = idx.top_by_coverage(2)
    assert [r.subtopic for r in top] == ["Limits", "Kinematics"]  # counts 50, 40


def test_default_subject_is_highest_total_coverage(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    # Mathematics total = 100, Physics = 40
    assert idx.default_subject() == "Mathematics"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_topic_index.py -q`
Expected: FAIL — `ModuleNotFoundError: ml_pipeline.services.topic_index`.

- [ ] **Step 4: Write minimal implementation** — create `ml_pipeline/services/topic_index.py`

```python
"""Shared topic index for the guidance engines.

Loads the processed parquet once, builds a TF-IDF index over the topic
hierarchy, and aggregates a difficulty label per subtopic from the flashcards
dataset. Framework-free and classical (scikit-learn TF-IDF only).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer

from .. import config

_DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}
_SAMPLE_QUESTIONS_PER_SUBTOPIC = 20


@dataclass(frozen=True)
class TopicRow:
    subject: str
    topic: str
    subtopic: str
    count: int
    difficulty: str


def _majority_difficulty(values) -> str:
    """Most common valid difficulty label; ties break to the easier label."""
    vals = [str(v).strip().lower() for v in values]
    vals = [v for v in vals if v in _DIFFICULTY_RANK]
    if not vals:
        return "medium"
    counts = Counter(vals)
    best = max(counts.items(), key=lambda kv: (kv[1], -_DIFFICULTY_RANK[kv[0]]))
    return best[0]


class TopicIndex:
    def __init__(self, rows, vectorizer, matrix):
        self._rows = rows
        self._vectorizer = vectorizer
        self._matrix = matrix  # TF-IDF matrix aligned row-for-row with self._rows

    @classmethod
    def from_frames(cls, hierarchy_df, flashcards_df) -> "TopicIndex":
        diff_map, q_map = {}, {}
        if flashcards_df is not None and len(flashcards_df):
            has_diff = "difficulty" in flashcards_df.columns
            has_q = "question" in flashcards_df.columns
            group_cols = ["subject", "topic", "subtopic"]
            if all(c in flashcards_df.columns for c in group_cols):
                for key, grp in flashcards_df.groupby(group_cols):
                    if has_diff:
                        diff_map[key] = _majority_difficulty(grp["difficulty"])
                    if has_q:
                        q_map[key] = " ".join(
                            str(x) for x in grp["question"].head(_SAMPLE_QUESTIONS_PER_SUBTOPIC)
                        )

        rows, corpus = [], []
        for r in hierarchy_df.itertuples(index=False):
            key = (r.subject, r.topic, r.subtopic)
            rows.append(TopicRow(
                subject=r.subject, topic=r.topic, subtopic=r.subtopic,
                count=int(getattr(r, "count", 0) or 0),
                difficulty=diff_map.get(key, "medium"),
            ))
            corpus.append(f"{r.subject} {r.topic} {r.subtopic} {q_map.get(key, '')}".strip())

        vectorizer = TfidfVectorizer(
            max_features=config.TFIDF_MAX_FEATURES,
            ngram_range=config.TFIDF_NGRAM,
            stop_words="english",
        )
        matrix = vectorizer.fit_transform(corpus) if corpus else None
        return cls(rows, vectorizer, matrix)

    @classmethod
    def load(cls) -> "TopicIndex":
        from ..dataset_loader import load_processed
        return cls.from_frames(load_processed("topic_hierarchy"), load_processed("flashcards"))

    def search(self, text: str, n: int):
        if not text or not text.strip() or self._matrix is None:
            return []
        q = self._vectorizer.transform([text])
        sims = (self._matrix @ q.T).toarray().ravel()  # TF-IDF is L2-normed => cosine
        order = sorted(range(len(self._rows)), key=lambda i: (-sims[i], self._rows[i].subtopic))
        return [(self._rows[i], float(sims[i])) for i in order[:n] if sims[i] > 0]

    def top_by_coverage(self, n: int):
        return sorted(self._rows, key=lambda r: (-r.count, r.subtopic))[:n]

    def rows_for_subject(self, subject: str):
        return [r for r in self._rows if r.subject == subject]

    def subjects(self):
        return sorted({r.subject for r in self._rows})

    def default_subject(self):
        if not self._rows:
            return None
        totals = defaultdict(int)
        for r in self._rows:
            totals[r.subject] += r.count
        return max(sorted(totals), key=lambda s: totals[s])

    def difficulty_for(self, subject, topic, subtopic) -> str:
        for r in self._rows:
            if (r.subject, r.topic, r.subtopic) == (subject, topic, subtopic):
                return r.difficulty
        return "medium"


@lru_cache(maxsize=1)
def get_topic_index() -> TopicIndex:
    """Process-memoized singleton. Raises if the processed parquet is missing."""
    return TopicIndex.load()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_topic_index.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add ml_pipeline/services/topic_index.py tests/test_topic_index.py tests/conftest.py
git commit -m "feat(ml): TopicIndex — shared TF-IDF + difficulty index for guidance"
```

---

## Task 2: RecommendationEngine.build_performance_profile

**Files:**
- Create: `ml_pipeline/services/recommendation_engine.py`
- Test: `tests/test_recommendation_engine.py`

**Interfaces:**
- Consumes: `ml_pipeline.services.topic_index` (`TopicIndex`, `get_topic_index`)
- Produces: `class RecommendationEngine`:
  - `RecommendationEngine(index: TopicIndex | None = None)` — uses injected index or the memoized singleton
  - `.build_performance_profile(flashcards=None, quiz_attempts=None) -> dict` returning
    `{"by_topic": {lower_name: {"n": int, "accuracy": float}}, "overall_accuracy": float | None}`

- [ ] **Step 1: Write the failing test** `tests/test_recommendation_engine.py`

```python
from collections import namedtuple

from ml_pipeline.services.recommendation_engine import RecommendationEngine
from ml_pipeline.services.topic_index import TopicIndex

_Topic = namedtuple("Topic", ["name"])
_Card = namedtuple("Card", ["correct_count", "incorrect_count", "topic"])
_Quiz = namedtuple("Quiz", ["topic"])
_Attempt = namedtuple("Attempt", ["score", "quiz"])


def _engine(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    return RecommendationEngine(index=idx)


def test_profile_aggregates_flashcard_accuracy(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    cards = [
        _Card(correct_count=2, incorrect_count=8, topic=_Topic("Calculus")),  # 0.2
        _Card(correct_count=9, incorrect_count=1, topic=_Topic("Algebra")),   # 0.9
        _Card(correct_count=0, incorrect_count=0, topic=_Topic("Ignored")),   # no data -> skipped
    ]
    profile = eng.build_performance_profile(flashcards=cards, quiz_attempts=[])
    assert profile["by_topic"]["calculus"]["accuracy"] == 0.2
    assert profile["by_topic"]["algebra"]["accuracy"] == 0.9
    assert "ignored" not in profile["by_topic"]
    assert profile["overall_accuracy"] == 0.55


def test_profile_includes_quiz_scores(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    attempts = [_Attempt(score=40.0, quiz=_Quiz(topic=_Topic("Mechanics")))]  # 0.4
    profile = eng.build_performance_profile(flashcards=[], quiz_attempts=attempts)
    assert profile["by_topic"]["mechanics"]["accuracy"] == 0.4


def test_empty_profile_is_valid(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    profile = eng.build_performance_profile(flashcards=[], quiz_attempts=[])
    assert profile == {"by_topic": {}, "overall_accuracy": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_recommendation_engine.py -q`
Expected: FAIL — `ModuleNotFoundError: ml_pipeline.services.recommendation_engine`.

- [ ] **Step 3: Write minimal implementation** — create `ml_pipeline/services/recommendation_engine.py`

```python
"""Content-based study recommendations over the topic hierarchy, weighted by
the student's performance profile. Framework-free; classical TF-IDF only.
"""
from __future__ import annotations

from .topic_index import TopicIndex, get_topic_index

CANDIDATE_MULTIPLIER = 4
WEAK_ACCURACY_THRESHOLD = 0.6
STRONG_ACCURACY_THRESHOLD = 0.85
WEAK_WEIGHT = 1.5
STRONG_WEIGHT = 0.6


class RecommendationEngine:
    def __init__(self, index: TopicIndex | None = None):
        self._index = index

    @property
    def index(self) -> TopicIndex:
        return self._index if self._index is not None else get_topic_index()

    def build_performance_profile(self, flashcards=None, quiz_attempts=None) -> dict:
        by_topic = {}   # lower_name -> [accuracy_sum, n]
        all_acc = []

        def _add(topic_name, accuracy):
            key = (topic_name or "").strip().lower() or "__untagged__"
            slot = by_topic.setdefault(key, [0.0, 0])
            slot[0] += accuracy
            slot[1] += 1
            all_acc.append(accuracy)

        for fc in (flashcards or []):
            correct = int(getattr(fc, "correct_count", 0) or 0)
            incorrect = int(getattr(fc, "incorrect_count", 0) or 0)
            seen = correct + incorrect
            if seen <= 0:
                continue
            topic = getattr(getattr(fc, "topic", None), "name", None)
            _add(topic, correct / seen)

        for qa in (quiz_attempts or []):
            score = getattr(qa, "score", None)
            if score is None:
                continue
            frac = score / 100.0 if score > 1 else float(score)
            quiz = getattr(qa, "quiz", None)
            topic = getattr(getattr(quiz, "topic", None), "name", None)
            _add(topic, max(0.0, min(1.0, frac)))

        return {
            "by_topic": {
                k: {"n": n, "accuracy": s / n}
                for k, (s, n) in by_topic.items() if n > 0
            },
            "overall_accuracy": (sum(all_acc) / len(all_acc)) if all_acc else None,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_recommendation_engine.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/services/recommendation_engine.py tests/test_recommendation_engine.py
git commit -m "feat(ml): RecommendationEngine.build_performance_profile"
```

---

## Task 3: RecommendationEngine.recommend_from_text

**Files:**
- Modify: `ml_pipeline/services/recommendation_engine.py`
- Test: `tests/test_recommendation_engine.py` (add tests)

**Interfaces:**
- Consumes: `TopicIndex.search`, `TopicIndex.top_by_coverage`, the profile from Task 2
- Produces: `RecommendationEngine.recommend_from_text(study_text: str, performance_by_topic: dict = None, n: int = 5) -> list[dict]` where each dict has keys `subject, topic, subtopic, label, priority (float), recommended_difficulty, reason`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_recommendation_engine.py`)

```python
def test_warm_path_ranks_relevant_subtopic_top(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    recs = eng.recommend_from_text("continuity of a function", performance_by_topic={}, n=3)
    assert recs
    assert recs[0]["subtopic"] == "Continuity"
    assert set(recs[0]) == {
        "subject", "topic", "subtopic", "label",
        "priority", "recommended_difficulty", "reason",
    }
    assert recs[0]["recommended_difficulty"] in {"easy", "medium", "hard"}


def test_cold_path_returns_coverage_order(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    recs = eng.recommend_from_text("", performance_by_topic={}, n=2)
    assert [r["subtopic"] for r in recs] == ["Limits", "Kinematics"]  # counts 50, 40
    assert all("Foundational" in r["reason"] for r in recs)


def test_weakness_weighting_boosts_priority(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)

    def poly_priority(recs):
        return next(r["priority"] for r in recs if r["subtopic"] == "Polynomials")

    neutral = eng.recommend_from_text("", performance_by_topic={}, n=4)
    # Algebra (Polynomials' parent topic) is weak -> Polynomials should be boosted.
    weak = {"by_topic": {"algebra": {"n": 5, "accuracy": 0.1}}, "overall_accuracy": 0.1}
    boosted = eng.recommend_from_text("", performance_by_topic=weak, n=4)

    assert poly_priority(boosted) > poly_priority(neutral)
    poly = next(r for r in boosted if r["subtopic"] == "Polynomials")
    assert "scoring lower" in poly["reason"]


def test_recommend_empty_when_index_has_no_rows():
    import pandas as pd
    from ml_pipeline.services.topic_index import TopicIndex
    empty = TopicIndex.from_frames(
        pd.DataFrame(columns=["subject", "topic", "subtopic", "count"]), pd.DataFrame())
    eng = RecommendationEngine(index=empty)
    assert eng.recommend_from_text("anything", performance_by_topic={}, n=5) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_recommendation_engine.py -q`
Expected: FAIL — `AttributeError: 'RecommendationEngine' object has no attribute 'recommend_from_text'`.

- [ ] **Step 3: Write minimal implementation** — append methods to `RecommendationEngine`

```python
    def recommend_from_text(self, study_text: str, performance_by_topic: dict = None, n: int = 5) -> list[dict]:
        idx = self.index
        by_topic = (performance_by_topic or {}).get("by_topic", {})
        k = max(1, n) * CANDIDATE_MULTIPLIER

        warm = bool(study_text and study_text.strip())
        if warm:
            candidates = list(idx.search(study_text, k))              # [(row, relevance)]
        else:
            rows = idx.top_by_coverage(k)
            max_count = max((r.count for r in rows), default=1) or 1
            candidates = [(r, r.count / max_count) for r in rows]

        scored = []
        for row, relevance in candidates:
            weight, weak = self._weakness_weight(row, by_topic)
            scored.append((relevance * weight, weak, row))

        scored.sort(key=lambda t: (-t[0], t[2].subtopic))

        out = []
        for priority, weak, row in scored[:n]:
            out.append({
                "subject": row.subject,
                "topic": row.topic,
                "subtopic": row.subtopic,
                "label": f"{row.topic} · {row.subtopic}",
                "priority": round(float(priority), 4),
                "recommended_difficulty": row.difficulty,
                "reason": self._reason(warm, weak, row),
            })
        return out

    @staticmethod
    def _weakness_weight(row, by_topic) -> tuple:
        for name in (row.subtopic, row.topic):
            entry = by_topic.get((name or "").strip().lower())
            if entry:
                acc = entry["accuracy"]
                if acc < WEAK_ACCURACY_THRESHOLD:
                    return WEAK_WEIGHT, True
                if acc >= STRONG_ACCURACY_THRESHOLD:
                    return STRONG_WEIGHT, False
                return 1.0, False
        return 1.0, False

    @staticmethod
    def _reason(warm: bool, weak: bool, row) -> str:
        if weak:
            return f"You've been scoring lower on {row.topic}"
        if warm:
            return "Closely matches your study notes"
        return f"Foundational topic in {row.subject}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_recommendation_engine.py -q`
Expected: PASS (7 tests total).

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/services/recommendation_engine.py tests/test_recommendation_engine.py
git commit -m "feat(ml): RecommendationEngine.recommend_from_text (warm/cold + weakness weighting)"
```

---

## Task 4: LearningPathEngine

**Files:**
- Create: `ml_pipeline/services/learning_path.py`
- Test: `tests/test_learning_path.py`

**Interfaces:**
- Consumes: `TopicIndex` (`rows_for_subject`, `default_subject`), the profile from Task 2
- Produces: `class LearningPathEngine`:
  - `LearningPathEngine(index: TopicIndex | None = None)`
  - `.estimate_mastery_from_performance(profile: dict) -> set[str]` (lowercased names)
  - `.get_learning_path(subject=None, mastered_subtopics=None, limit=15) -> list[dict]` with keys `step, subject, topic, subtopic, difficulty, status`

- [ ] **Step 1: Write the failing test** `tests/test_learning_path.py`

```python
from ml_pipeline.services.learning_path import LearningPathEngine
from ml_pipeline.services.topic_index import TopicIndex


def _engine(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    return LearningPathEngine(index=idx)


def test_mastery_requires_threshold_and_min_points(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    profile = {"by_topic": {
        "limits": {"n": 3, "accuracy": 0.9},     # mastered
        "continuity": {"n": 1, "accuracy": 1.0},  # too few points -> not mastered
        "algebra": {"n": 5, "accuracy": 0.5},     # below threshold -> not mastered
    }, "overall_accuracy": 0.7}
    mastered = eng.estimate_mastery_from_performance(profile)
    assert mastered == {"limits"}


def test_learning_path_orders_easy_to_hard_then_coverage(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    path = eng.get_learning_path(subject="Mathematics", mastered_subtopics=set(), limit=10)
    # Mathematics subtopics: Limits(easy,50), Polynomials(medium,20), Continuity(hard,30)
    assert [s["subtopic"] for s in path] == ["Limits", "Polynomials", "Continuity"]
    assert [s["step"] for s in path] == [1, 2, 3]
    assert path[0]["status"] == "current"     # first non-mastered
    assert path[1]["status"] == "upcoming"
    assert set(path[0]) == {"step", "subject", "topic", "subtopic", "difficulty", "status"}


def test_learning_path_marks_mastered_and_current(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    path = eng.get_learning_path(subject="Mathematics", mastered_subtopics={"limits"}, limit=10)
    by_sub = {s["subtopic"]: s for s in path}
    assert by_sub["Limits"]["status"] == "mastered"
    assert by_sub["Polynomials"]["status"] == "current"  # first non-mastered
    assert by_sub["Continuity"]["status"] == "upcoming"


def test_default_subject_when_none(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    path = eng.get_learning_path(subject=None, mastered_subtopics=set(), limit=10)
    assert path and all(s["subject"] == "Mathematics" for s in path)  # highest coverage


def test_learning_path_respects_limit(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    path = eng.get_learning_path(subject="Mathematics", mastered_subtopics=set(), limit=2)
    assert len(path) == 2


def test_learning_path_empty_for_unknown_subject(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    assert eng.get_learning_path(subject="Chemistry", mastered_subtopics=set(), limit=5) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_learning_path.py -q`
Expected: FAIL — `ModuleNotFoundError: ml_pipeline.services.learning_path`.

- [ ] **Step 3: Write minimal implementation** — create `ml_pipeline/services/learning_path.py`

```python
"""Adaptive learning path over the topic hierarchy. Framework-free.

Orders a subject's subtopics easy -> hard, then by coverage, and marks each as
mastered / current / upcoming based on the student's estimated mastery.
"""
from __future__ import annotations

from .topic_index import TopicIndex, get_topic_index

MASTERY_THRESHOLD = 0.8
MIN_MASTERY_POINTS = 2
DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}


class LearningPathEngine:
    def __init__(self, index: TopicIndex | None = None):
        self._index = index

    @property
    def index(self) -> TopicIndex:
        return self._index if self._index is not None else get_topic_index()

    def estimate_mastery_from_performance(self, profile: dict) -> set:
        by_topic = (profile or {}).get("by_topic", {})
        return {
            key for key, stat in by_topic.items()
            if stat.get("n", 0) >= MIN_MASTERY_POINTS
            and stat.get("accuracy", 0.0) >= MASTERY_THRESHOLD
        }

    def get_learning_path(self, subject=None, mastered_subtopics=None, limit: int = 15) -> list[dict]:
        idx = self.index
        subject = subject or idx.default_subject()
        if not subject:
            return []
        rows = idx.rows_for_subject(subject)
        if not rows:
            return []

        mastered = {str(m).strip().lower() for m in (mastered_subtopics or [])}
        ordered = sorted(
            rows, key=lambda r: (DIFFICULTY_ORDER.get(r.difficulty, 1), -r.count, r.subtopic))

        steps, current_assigned = [], False
        for i, row in enumerate(ordered[:limit], start=1):
            is_mastered = (
                row.subtopic.strip().lower() in mastered
                or row.topic.strip().lower() in mastered
            )
            if is_mastered:
                status = "mastered"
            elif not current_assigned:
                status = "current"
                current_assigned = True
            else:
                status = "upcoming"
            steps.append({
                "step": i,
                "subject": row.subject,
                "topic": row.topic,
                "subtopic": row.subtopic,
                "difficulty": row.difficulty,
                "status": status,
            })
        return steps
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_learning_path.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/services/learning_path.py tests/test_learning_path.py
git commit -m "feat(ml): LearningPathEngine — mastery estimate + ordered path"
```

---

## Task 5: Package exports + real-data integration + adapter smoke

**Files:**
- Modify: `ml_pipeline/services/__init__.py`
- Test: `tests/test_guidance_integration.py`

**Interfaces:**
- Consumes: `RecommendationEngine`, `LearningPathEngine`, real processed parquet via `get_topic_index`
- Produces: `ml_pipeline.services` exports `RecommendationEngine`, `LearningPathEngine`

- [ ] **Step 1: Update `ml_pipeline/services/__init__.py`**

Replace the placeholder docstring file with:

```python
"""Guidance services for the ML pipeline (recommendations + learning path).

Note: generation services (flashcard/quiz) are a later spec and are imported
lazily by the Django adapter, so they are intentionally not re-exported here.
"""
from .learning_path import LearningPathEngine
from .recommendation_engine import RecommendationEngine

__all__ = ["RecommendationEngine", "LearningPathEngine"]
```

- [ ] **Step 2: Write the integration test** `tests/test_guidance_integration.py`

```python
"""End-to-end against the REAL processed parquet (datasets/processed/*.parquet).

Skips cleanly if the processed data has not been built yet.
"""
import pytest

from ml_pipeline import config
from ml_pipeline.services import LearningPathEngine, RecommendationEngine
from ml_pipeline.services.topic_index import TopicIndex

pytestmark = pytest.mark.skipif(
    not config.PROCESSED_FILES["topic_hierarchy"].exists()
    or not config.PROCESSED_FILES["flashcards"].exists(),
    reason="processed parquet not built yet",
)


@pytest.fixture(scope="module")
def real_index():
    return TopicIndex.load()


def test_recommendations_have_valid_shape_on_real_data(real_index):
    eng = RecommendationEngine(index=real_index)
    # Query with a real topic+subtopic drawn from the index, so the relevance
    # assertion is independent of the actual taxonomy contents.
    sample = real_index.top_by_coverage(1)[0]
    recs = eng.recommend_from_text(
        f"{sample.topic} {sample.subtopic}", performance_by_topic={}, n=5)
    assert recs, "expected non-empty recommendations on real data"
    for r in recs:
        assert set(r) == {
            "subject", "topic", "subtopic", "label",
            "priority", "recommended_difficulty", "reason",
        }
        assert r["recommended_difficulty"] in {"easy", "medium", "hard"}
    # querying a real topic surfaces that topic/subtopic in the top results
    assert any(
        r["topic"] == sample.topic or r["subtopic"] == sample.subtopic for r in recs)


def test_cold_recommendations_non_empty_on_real_data(real_index):
    eng = RecommendationEngine(index=real_index)
    recs = eng.recommend_from_text("", performance_by_topic={}, n=5)
    assert len(recs) == 5


def test_learning_path_valid_shape_on_real_data(real_index):
    eng = LearningPathEngine(index=real_index)
    path = eng.get_learning_path(subject=None, mastered_subtopics=set(), limit=12)
    assert path, "expected a non-empty default-subject path"
    statuses = {s["status"] for s in path}
    assert statuses <= {"mastered", "current", "upcoming"}
    assert [s["step"] for s in path] == list(range(1, len(path) + 1))
```

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: ALL tests PASS (Tasks 1–5, including foundation tests).

- [ ] **Step 4: Verify the Django adapter contract (manual, one-off)**

The analytics endpoints call `ml.adapter.get_study_recommendations` / `get_learning_path`, which import these engines. Confirm the import + call path resolves. Run from `backend/` with the pipeline importable (needs Django in the venv; if absent, Step 3's integration test is the authoritative check):

```bash
cd backend && ../.venv/bin/python -c "import sys; sys.path.insert(0,'..'); from ml_pipeline.services import RecommendationEngine, LearningPathEngine; from ml_pipeline.services.topic_index import get_topic_index; idx=get_topic_index(); print('recs:', len(RecommendationEngine(index=idx).recommend_from_text('cell biology', {}, 5))); print('path:', len(LearningPathEngine(index=idx).get_learning_path(None, set(), 12)))"
```
Expected: prints non-zero `recs:` and `path:` counts without error.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/services/__init__.py tests/test_guidance_integration.py
git commit -m "feat(ml): export guidance engines + real-data integration tests"
```

---

## Self-Review

**Spec coverage:**
- §3 contract (method signatures + output keys) → Tasks 2/3 (RecommendationEngine), 4 (LearningPathEngine); keys asserted in tests. ✓
- §4 module layout (topic_index + 2 engines) → Tasks 1/2/3/4; `__init__` exports Task 5. ✓
- §5.1 TopicIndex (load-once, TF-IDF, difficulty aggregation, search/coverage/subject/difficulty) → Task 1. ✓
- §5.2 profile + warm/cold + weakness weighting + reason → Tasks 2, 3. ✓
- §5.3 mastery threshold+min-points, easy→hard→coverage order, status, default subject, limit → Task 4. ✓
- §6 data flow (adapter → engines → TopicIndex) → Task 5 adapter smoke. ✓
- §7 durability: memoized singleton (`get_topic_index` lru_cache, Task 1); return `[]` on cold/empty (Tasks 3/4 tests); raise on genuine load failure (`get_topic_index`/`load`); missing difficulty → medium (Task 1 test); determinism via stable tie-broken sorts. ✓
- §8 testing incl. real-data integration + adapter check → Task 5. ✓
- §9 acceptance 1–8 → Tasks 1–5 verification steps. ✓
- §10 out of scope: generation not touched; `__init__` deliberately does not import generators. ✓

**Placeholder scan:** No TBD/TODO; every code step contains complete code. ✓

**Type consistency:** `TopicRow`, `TopicIndex.from_frames/search/top_by_coverage/rows_for_subject/default_subject/difficulty_for`, `get_topic_index`, `RecommendationEngine(index=)/.build_performance_profile/.recommend_from_text/._weakness_weight/._reason`, `LearningPathEngine(index=)/.estimate_mastery_from_performance/.get_learning_path`, profile shape `{"by_topic": {name: {"n","accuracy"}}, "overall_accuracy"}`, and the two output dict key sets are consistent across Tasks 1–5 and match spec §3. ✓

**Note for implementer:** Task 5 Step 3/4 run against the real `datasets/processed/*.parquet` (already built by the foundation). The unit tests (Tasks 1–4) are fully DB-free and parquet-free via injected `TopicIndex(index=...)`.
