# ML Generation Services Implementation Plan

**Goal:** Implement `FlashcardGenerator` and `QuizGenerator` (plus a shared `ContentExtractor`) under `ml_pipeline/services/` so the app can generate study material from source text locally, with the trained `AnswerScorer` gating quiz quality.

**Architecture:** A shared, spaCy-based `ContentExtractor` turns source text into ranked `Candidate`s (a salient sentence + its key term + entity label). `FlashcardGenerator` builds definitional/cloze cards; `QuizGenerator` builds cloze MCQs, generates distractors, and drops any question whose correct answer the `AnswerScorer` doesn't rank #1. Classical + local only.

**Tech Stack:** Python 3.11, spaCy 3.8 (`en_core_web_sm`), scikit-learn TF-IDF, textstat, joblib, pytest.

## Global Constraints

- `ml_pipeline` stays **Django-free** (no Django imports). Generators take plain `text` and return plain dict/list structures.
- **Classical + local only** — spaCy + scikit-learn + textstat + the trained `AnswerScorer`. No LLM, no network.
- **Signatures fixed** by `backend/ml/adapter.py`; **output keys fixed** by the adapter + `generate.py` save loop:
  - `FlashcardGenerator.generate(text, count, title) -> list[dict]`, each `{"question", "answer", "difficulty"}`.
  - `QuizGenerator.generate(text, question_count, title) -> {"title", "description", "questions": [{"question_text", "question_type", "options", "correct_answer", "explanation"}]}`.
- **Quality over quantity:** return only validated items, up to the requested count; never pad; empty when nothing valid.
- **Definitional stem is generic `"What is {term}?"`** — never label-specific Who/When/Where (spaCy mislabels study terms).
- Every emitted quiz question must pass the AnswerScorer gate (correct answer ranks #1 among options).
- **Deterministic:** seed shuffles with `config.RANDOM_SEED`; stable tie-broken sorts.
- Memoized singletons `get_nlp()` / `get_answer_scorer()`; raise on genuine load failure (adapter falls back).
- Tunables as named constants at module tops.
- Repo venv: `.venv/bin/python` / `.venv/bin/pytest`.

---

## Task 1: ContentExtractor (shared spine) + difficulty + fixtures

**Files:**
- Create: `ml_pipeline/services/content_extractor.py`
- Modify: `tests/conftest.py` (add generation fixtures: `Candidate` builders, `FakeExtractor`, `FakeScorer`, sample text)
- Test: `tests/test_content_extractor.py`

**Interfaces:**
- Consumes: spaCy `en_core_web_sm`, `sklearn.feature_extraction.text.TfidfVectorizer`, `textstat`
- Produces:
  - `@dataclass(frozen=True) Candidate(sentence: str, term: str, label: str, score: float)`
  - `get_nlp()` — memoized spaCy pipeline (raises if model missing)
  - `DEFINITIONAL_LABELS`, `NUMERIC_LABELS`, `ANSWERABLE_ENT_LABELS`, `NOUN_CHUNK_LABEL` constants
  - `class ContentExtractor(nlp=None)` with `.extract_candidates(text: str, max_candidates: int) -> list[Candidate]`
  - `difficulty_for(candidate: Candidate) -> str` (one of easy/medium/hard)

- [ ] **Step 1: Add generation fixtures to `tests/conftest.py`** (append)

```python
from ml_pipeline.services.content_extractor import Candidate


@pytest.fixture
def sample_candidates():
    """Deterministic Candidates for generator unit tests (no spaCy needed)."""
    return [
        Candidate(sentence="Mitochondria are the powerhouse of the cell.",
                  term="powerhouse", label="NOUN_CHUNK", score=3.0),
        Candidate(sentence="Albert Einstein developed the theory of relativity.",
                  term="Albert Einstein", label="PERSON", score=2.5),
        Candidate(sentence="Photosynthesis converts sunlight into chemical energy.",
                  term="Photosynthesis", label="NOUN_CHUNK", score=2.0),
        Candidate(sentence="Water boils at 100 degrees Celsius at sea level.",
                  term="100 degrees Celsius", label="QUANTITY", score=1.5),
    ]


class FakeExtractor:
    """Returns a fixed candidate list, ignoring the text."""
    def __init__(self, candidates):
        self._candidates = candidates

    def extract_candidates(self, text, max_candidates):
        return list(self._candidates)[:max_candidates]


class FakeScorer:
    """Deterministic AnswerScorer stub. Ranks `winner` first if present."""
    def __init__(self, winner=None):
        self.winner = winner

    def rank(self, question, candidates, support):
        cands = list(candidates)
        if self.winner in cands:
            cands = [self.winner] + [c for c in cands if c != self.winner]
        return [(c, 1.0 - i * 0.1) for i, c in enumerate(cands)]


@pytest.fixture
def fake_extractor_factory():
    return FakeExtractor


@pytest.fixture
def fake_scorer_factory():
    return FakeScorer
```

- [ ] **Step 2: Write the failing test** `tests/test_content_extractor.py`

```python
from ml_pipeline.services.content_extractor import (
    Candidate, ContentExtractor, difficulty_for, DEFINITIONAL_LABELS,
)


def test_extract_pulls_named_entity_as_term():
    ext = ContentExtractor()
    cands = ext.extract_candidates(
        "Albert Einstein developed the theory of relativity in 1905.", max_candidates=5)
    assert cands
    einstein = [c for c in cands if c.term == "Albert Einstein"]
    assert einstein and einstein[0].label == "PERSON"
    # the term is a contiguous span of its support sentence
    assert einstein[0].term in einstein[0].sentence


def test_extract_falls_back_to_noun_chunk_when_no_entity():
    ext = ContentExtractor()
    cands = ext.extract_candidates(
        "Photosynthesis converts sunlight into chemical energy in plants.", max_candidates=5)
    assert cands
    c = cands[0]
    assert c.term and c.term in c.sentence
    assert c.label  # some label assigned


def test_extract_dedupes_and_respects_max():
    ext = ContentExtractor()
    text = ("The cell contains a nucleus. The cell contains a nucleus. "
            "Ribosomes build proteins inside the cell.")
    cands = ext.extract_candidates(text, max_candidates=2)
    assert len(cands) <= 2
    terms = [c.term.lower() for c in cands]
    assert len(terms) == len(set(terms))  # no duplicate terms


def test_extract_empty_or_thin_text_returns_empty():
    ext = ContentExtractor()
    assert ext.extract_candidates("", max_candidates=5) == []
    assert ext.extract_candidates("Yes.", max_candidates=5) == []  # too short
    assert ext.extract_candidates("x y z", max_candidates=0) == []


def test_difficulty_for_returns_valid_bucket():
    c = Candidate(sentence="The cat sat on the mat.", term="cat",
                  label="NOUN_CHUNK", score=1.0)
    assert difficulty_for(c) in {"easy", "medium", "hard"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_content_extractor.py -q`
Expected: FAIL — `ModuleNotFoundError: ml_pipeline.services.content_extractor`.

- [ ] **Step 4: Write minimal implementation** — create `ml_pipeline/services/content_extractor.py`

```python
"""Shared content extraction for the generation services (classical, local).

spaCy for sentence segmentation + key terms; TF-IDF for sentence salience.
Framework-free; no LLM/network.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import textstat
from sklearn.feature_extraction.text import TfidfVectorizer

# Nominal entities that read well as "What is {term}?" definitional cards.
DEFINITIONAL_LABELS = {
    "PERSON", "ORG", "GPE", "LOC", "NORP", "FAC", "EVENT",
    "WORK_OF_ART", "PRODUCT", "LAW", "LANGUAGE",
}
# Numeric/temporal entities that read better as cloze.
NUMERIC_LABELS = {"DATE", "TIME", "PERCENT", "MONEY", "QUANTITY", "ORDINAL", "CARDINAL"}
ANSWERABLE_ENT_LABELS = DEFINITIONAL_LABELS | NUMERIC_LABELS
NOUN_CHUNK_LABEL = "NOUN_CHUNK"

MIN_SENT_TOKENS = 5
MAX_SENT_TOKENS = 40
MAX_TEXT_CHARS = 100_000

# Difficulty thresholds on Flesch reading-ease (higher = easier to read).
EASY_READING_EASE = 60.0
HARD_READING_EASE = 30.0


@dataclass(frozen=True)
class Candidate:
    sentence: str
    term: str
    label: str
    score: float


@lru_cache(maxsize=1)
def get_nlp():
    """Memoized spaCy pipeline. Raises if en_core_web_sm is unavailable."""
    import spacy
    return spacy.load("en_core_web_sm")


def difficulty_for(candidate: "Candidate") -> str:
    """Bucket difficulty from the support sentence's reading ease."""
    text = candidate.sentence or ""
    if not text.strip():
        return "medium"
    ease = textstat.flesch_reading_ease(text)
    if ease >= EASY_READING_EASE:
        return "easy"
    if ease <= HARD_READING_EASE:
        return "hard"
    return "medium"


class ContentExtractor:
    def __init__(self, nlp=None):
        self._nlp = nlp

    @property
    def nlp(self):
        return self._nlp if self._nlp is not None else get_nlp()

    def extract_candidates(self, text: str, max_candidates: int) -> list[Candidate]:
        text = (text or "")[:MAX_TEXT_CHARS].strip()
        if not text or max_candidates <= 0:
            return []
        doc = self.nlp(text)
        sents = [s for s in doc.sents
                 if MIN_SENT_TOKENS <= sum(1 for t in s if not t.is_space) <= MAX_SENT_TOKENS]
        if not sents:
            return []

        sent_texts = [s.text.strip() for s in sents]
        try:
            vec = TfidfVectorizer(stop_words="english")
            matrix = vec.fit_transform(sent_texts)
        except ValueError:
            return []  # empty vocabulary (all stopwords)
        salience = np.asarray(matrix.sum(axis=1)).ravel()
        idf, vocab = vec.idf_, vec.vocabulary_

        order = sorted(range(len(sents)), key=lambda i: (-salience[i], sent_texts[i]))
        out, seen = [], set()
        for i in order:
            picked = self._pick_term(sents[i], idf, vocab)
            if picked is None:
                continue
            term, label = picked
            key = term.lower()
            if key in seen or term not in sent_texts[i]:
                continue
            seen.add(key)
            out.append(Candidate(sentence=sent_texts[i], term=term, label=label,
                                 score=float(salience[i])))
            if len(out) >= max_candidates:
                break
        return out

    @staticmethod
    def _pick_term(sent, idf, vocab):
        """Prefer an answerable named entity; else the highest-IDF noun chunk
        (determiners stripped)."""
        for ent in sent.ents:
            if ent.label_ in ANSWERABLE_ENT_LABELS and ent.text.strip():
                return ent.text.strip(), ent.label_
        best, best_w = None, -1.0
        for chunk in sent.noun_chunks:
            root = chunk.root
            if root.is_stop or root.pos_ == "PRON":
                continue
            phrase = " ".join(t.text for t in chunk if t.pos_ != "DET").strip()
            if not phrase:
                continue
            w = idf[vocab[root.text.lower()]] if root.text.lower() in vocab else 0.0
            if w > best_w:
                best, best_w = phrase, w
        return (best, NOUN_CHUNK_LABEL) if best else None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_content_extractor.py -q`
Expected: PASS (5 tests). Note: first run loads spaCy (~1s).

- [ ] **Step 6: Commit**

```bash
git add ml_pipeline/services/content_extractor.py tests/test_content_extractor.py tests/conftest.py
git commit -m "feat(ml): ContentExtractor — shared spaCy/TF-IDF extraction + difficulty"
```

---

## Task 2: FlashcardGenerator

**Files:**
- Create: `ml_pipeline/services/flashcard_generator.py`
- Test: `tests/test_flashcard_generator.py`

**Interfaces:**
- Consumes: `ContentExtractor`, `difficulty_for`, `DEFINITIONAL_LABELS`, `Candidate` (Task 1); `FakeExtractor` (conftest)
- Produces: `class FlashcardGenerator(extractor=None)` with `.generate(text: str, count: int, title: str = "") -> list[dict]`, each dict `{"question", "answer", "difficulty"}`

- [ ] **Step 1: Write the failing test** `tests/test_flashcard_generator.py`

```python
from ml_pipeline.services.flashcard_generator import FlashcardGenerator


def _gen(candidates, fake_extractor_factory):
    return FlashcardGenerator(extractor=fake_extractor_factory(candidates))


def test_definitional_card_for_nominal_entity(sample_candidates, fake_extractor_factory):
    gen = _gen(sample_candidates, fake_extractor_factory)
    cards = gen.generate("ignored", count=10)
    einstein = [c for c in cards if c["answer"].startswith("Albert Einstein")]
    assert einstein
    assert einstein[0]["question"] == "What is Albert Einstein?"
    assert set(einstein[0]) == {"question", "answer", "difficulty"}
    assert einstein[0]["difficulty"] in {"easy", "medium", "hard"}


def test_cloze_card_for_noun_chunk(sample_candidates, fake_extractor_factory):
    gen = _gen(sample_candidates, fake_extractor_factory)
    cards = gen.generate("ignored", count=10)
    powerhouse = [c for c in cards if c["answer"] == "powerhouse"]
    assert powerhouse
    assert "______" in powerhouse[0]["question"]
    assert "powerhouse" not in powerhouse[0]["question"]


def test_count_is_respected(sample_candidates, fake_extractor_factory):
    gen = _gen(sample_candidates, fake_extractor_factory)
    assert len(gen.generate("ignored", count=2)) == 2


def test_zero_or_empty_returns_empty(sample_candidates, fake_extractor_factory):
    gen = _gen(sample_candidates, fake_extractor_factory)
    assert gen.generate("ignored", count=0) == []
    assert FlashcardGenerator(extractor=fake_extractor_factory([])).generate("x", count=5) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_flashcard_generator.py -q`
Expected: FAIL — `ModuleNotFoundError: ml_pipeline.services.flashcard_generator`.

- [ ] **Step 3: Write minimal implementation** — create `ml_pipeline/services/flashcard_generator.py`

```python
"""Flashcard generation from source text (classical, local; no LLM)."""
from __future__ import annotations

from .content_extractor import ContentExtractor, DEFINITIONAL_LABELS, difficulty_for

OVERSAMPLE = 3
BLANK = "______"


class FlashcardGenerator:
    def __init__(self, extractor=None):
        self._extractor = extractor

    @property
    def extractor(self):
        return self._extractor if self._extractor is not None else ContentExtractor()

    def generate(self, text: str, count: int, title: str = "") -> list[dict]:
        count = max(0, count)
        if count == 0:
            return []
        candidates = self.extractor.extract_candidates(text, count * OVERSAMPLE)
        cards = []
        for c in candidates:
            if c.label in DEFINITIONAL_LABELS:
                question, answer = f"What is {c.term}?", c.sentence
            else:
                question, answer = c.sentence.replace(c.term, BLANK, 1), c.term
            cards.append({"question": question, "answer": answer,
                          "difficulty": difficulty_for(c)})
            if len(cards) >= count:
                break
        return cards
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_flashcard_generator.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/services/flashcard_generator.py tests/test_flashcard_generator.py
git commit -m "feat(ml): FlashcardGenerator (definitional + cloze)"
```

---

## Task 3: QuizGenerator scaffolding — scorer loader + distractors

**Files:**
- Create: `ml_pipeline/services/quiz_generator.py`
- Test: `tests/test_quiz_distractors.py`

**Interfaces:**
- Consumes: `ml_pipeline.config`, `ml_pipeline.answer_scorer.AnswerScorer`, `ContentExtractor`, `Candidate`
- Produces:
  - `get_answer_scorer() -> AnswerScorer` (memoized; raises if artifact missing)
  - `class QuizGenerator(extractor=None, scorer=None)` with `.extractor` / `.scorer` properties
  - `QuizGenerator._distractors(candidate, candidates) -> list[str]` — same-source terms, same-label preferred, TF-IDF-ranked within group; excludes the correct term; deduped
  - `QuizGenerator._rank_by_similarity(term, terms) -> list[str]` — helper used by `_distractors`
  - Constants `OVERSAMPLE = 4`, `N_DISTRACTORS = 3`, `BLANK = "______"`

- [ ] **Step 1: Write the failing test** `tests/test_quiz_distractors.py`

```python
from ml_pipeline.services.content_extractor import Candidate
from ml_pipeline.services.quiz_generator import QuizGenerator


def _cands():
    return [
        Candidate("A sentence about dogs.", "dog", "NOUN_CHUNK", 3.0),
        Candidate("A sentence about cats.", "cat", "NOUN_CHUNK", 2.5),
        Candidate("A sentence about birds.", "bird", "NOUN_CHUNK", 2.0),
        Candidate("A sentence about fish.", "fish", "NOUN_CHUNK", 1.5),
        Candidate("Paris is a city.", "Paris", "GPE", 1.0),
    ]


def test_distractors_exclude_correct_and_are_from_source():
    cands = _cands()
    correct = cands[0]  # "dog"
    distractors = QuizGenerator._distractors(correct, cands)
    assert "dog" not in [d.lower() for d in distractors]
    source_terms = {c.term for c in cands}
    assert all(d in source_terms for d in distractors)


def test_distractors_prefer_same_label():
    cands = _cands()
    correct = cands[0]  # NOUN_CHUNK
    distractors = QuizGenerator._distractors(correct, cands)[:3]
    # top distractors should be the other NOUN_CHUNK terms, not the GPE "Paris"
    assert "Paris" not in distractors


def test_distractors_deduped():
    cands = [
        Candidate("s1", "dog", "NOUN_CHUNK", 3.0),
        Candidate("s2", "Dog", "NOUN_CHUNK", 2.0),  # dup by case
        Candidate("s3", "cat", "NOUN_CHUNK", 1.0),
    ]
    distractors = QuizGenerator._distractors(cands[0], cands)
    assert [d.lower() for d in distractors].count("dog") == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_quiz_distractors.py -q`
Expected: FAIL — `ModuleNotFoundError: ml_pipeline.services.quiz_generator`.

- [ ] **Step 3: Write minimal implementation** — create `ml_pipeline/services/quiz_generator.py`

```python
"""Quiz (MCQ) generation from source text, gated by the trained AnswerScorer."""
from __future__ import annotations

import random
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer

from .. import config
from ..answer_scorer import AnswerScorer
from .content_extractor import ContentExtractor

OVERSAMPLE = 4
N_DISTRACTORS = 3
BLANK = "______"


@lru_cache(maxsize=1)
def get_answer_scorer() -> AnswerScorer:
    """Memoized trained AnswerScorer. Raises if the artifact is missing."""
    return AnswerScorer.load(config.MODELS_DIR / "answer_scorer.joblib")


class QuizGenerator:
    def __init__(self, extractor=None, scorer=None):
        self._extractor = extractor
        self._scorer = scorer

    @property
    def extractor(self):
        return self._extractor if self._extractor is not None else ContentExtractor()

    @property
    def scorer(self):
        return self._scorer if self._scorer is not None else get_answer_scorer()

    @staticmethod
    def _distractors(candidate, candidates) -> list[str]:
        """Same-source terms, same label first, TF-IDF-ranked WITHIN each group so
        the same-label preference is preserved (not washed out by a global re-sort)."""
        same, other, seen = [], [], {candidate.term.lower()}
        for c in candidates:
            key = c.term.lower()
            if key in seen:
                continue
            seen.add(key)
            (same if c.label == candidate.label else other).append(c.term)
        return (QuizGenerator._rank_by_similarity(candidate.term, same)
                + QuizGenerator._rank_by_similarity(candidate.term, other))

    @staticmethod
    def _rank_by_similarity(term: str, terms: list[str]) -> list[str]:
        """Order `terms` by TF-IDF cosine similarity to `term` (desc, name tie-break)."""
        if len(terms) < 2:
            return list(terms)
        try:
            vec = TfidfVectorizer().fit([term] + terms)
            tm = vec.transform([term])
            om = vec.transform(terms)
            sims = (om @ tm.T).toarray().ravel()
        except ValueError:
            return list(terms)
        order = sorted(range(len(terms)), key=lambda i: (-sims[i], terms[i]))
        return [terms[i] for i in order]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_quiz_distractors.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/services/quiz_generator.py tests/test_quiz_distractors.py
git commit -m "feat(ml): QuizGenerator scaffolding — scorer loader + distractors"
```

---

## Task 4: QuizGenerator.generate — cloze MCQ + AnswerScorer gate

**Files:**
- Modify: `ml_pipeline/services/quiz_generator.py`
- Test: `tests/test_quiz_generator.py`

**Interfaces:**
- Consumes: `QuizGenerator._distractors`, `self.scorer.rank(question, candidates, support)`, `self.extractor`; `FakeExtractor`/`FakeScorer` (conftest)
- Produces: `QuizGenerator.generate(text: str, question_count: int, title: str = "") -> dict` with keys `title, description, questions`; each question `{question_text, question_type, options, correct_answer, explanation}`

- [ ] **Step 1: Write the failing test** `tests/test_quiz_generator.py`

```python
from ml_pipeline.services.content_extractor import Candidate
from ml_pipeline.services.quiz_generator import QuizGenerator


def _cands():
    return [
        Candidate("Mitochondria are the powerhouse of the cell.", "powerhouse", "NOUN_CHUNK", 3.0),
        Candidate("Ribosomes build proteins in the cell.", "Ribosomes", "NOUN_CHUNK", 2.5),
        Candidate("The nucleus stores genetic material.", "nucleus", "NOUN_CHUNK", 2.0),
        Candidate("Chloroplasts perform photosynthesis.", "Chloroplasts", "NOUN_CHUNK", 1.5),
    ]


def _gen(cands, winner, fake_extractor_factory, fake_scorer_factory):
    return QuizGenerator(extractor=fake_extractor_factory(cands),
                         scorer=fake_scorer_factory(winner=winner))


def test_valid_mcq_shape_when_gate_passes(fake_extractor_factory, fake_scorer_factory):
    cands = _cands()
    gen = _gen(cands, "powerhouse", fake_extractor_factory, fake_scorer_factory)
    data = gen.generate("ignored", question_count=1)
    assert set(data) == {"title", "description", "questions"}
    q = data["questions"][0]
    assert set(q) == {"question_text", "question_type", "options", "correct_answer", "explanation"}
    assert q["question_type"] == "multiple_choice"
    assert len(q["options"]) == 4
    assert q["correct_answer"] == "powerhouse"
    assert q["correct_answer"] in q["options"]
    assert "______" in q["question_text"]
    assert q["explanation"] == "Mitochondria are the powerhouse of the cell."


def test_gate_drops_question_when_correct_not_ranked_first(fake_extractor_factory, fake_scorer_factory):
    cands = _cands()
    # scorer makes a DISTRACTOR win -> every question should be dropped
    gen = _gen(cands, "Ribosomes", fake_extractor_factory, fake_scorer_factory)
    data = gen.generate("ignored", question_count=4)
    # "powerhouse" question: winner "Ribosomes" is a distractor -> dropped.
    # Only a question whose correct term == "Ribosomes" could survive.
    for q in data["questions"]:
        assert q["correct_answer"] == "Ribosomes"


def test_quality_over_quantity_returns_fewer(fake_extractor_factory, fake_scorer_factory):
    # Only two candidates -> can't form 3 distractors -> no valid questions.
    cands = [
        Candidate("A about x.", "x", "NOUN_CHUNK", 2.0),
        Candidate("B about y.", "y", "NOUN_CHUNK", 1.0),
    ]
    gen = _gen(cands, "x", fake_extractor_factory, fake_scorer_factory)
    assert gen.generate("ignored", question_count=5)["questions"] == []


def test_zero_count_returns_empty_questions(fake_extractor_factory, fake_scorer_factory):
    gen = _gen(_cands(), "powerhouse", fake_extractor_factory, fake_scorer_factory)
    assert gen.generate("ignored", question_count=0)["questions"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_quiz_generator.py -q`
Expected: FAIL — `AttributeError: 'QuizGenerator' object has no attribute 'generate'`.

- [ ] **Step 3: Write minimal implementation** — append `generate` to `QuizGenerator` in `ml_pipeline/services/quiz_generator.py`

```python
    def generate(self, text: str, question_count: int, title: str = "") -> dict:
        question_count = max(0, question_count)
        result = {
            "title": title or "Quiz",
            "description": f"Generated from {title}" if title else "Generated quiz",
            "questions": [],
        }
        if question_count == 0:
            return result

        candidates = self.extractor.extract_candidates(text, question_count * OVERSAMPLE)
        rng = random.Random(config.RANDOM_SEED)
        questions = []
        for c in candidates:
            distractors = self._distractors(c, candidates)
            if len(distractors) < N_DISTRACTORS:
                continue
            options = [c.term] + distractors[:N_DISTRACTORS]
            stem = c.sentence.replace(c.term, BLANK, 1)
            ranked = self.scorer.rank(stem, options, c.sentence)
            if not ranked or ranked[0][0] != c.term:
                continue  # AnswerScorer gate: correct answer must rank #1
            shuffled = list(options)
            rng.shuffle(shuffled)
            questions.append({
                "question_text": stem,
                "question_type": "multiple_choice",
                "options": shuffled,
                "correct_answer": c.term,
                "explanation": c.sentence,
            })
            if len(questions) >= question_count:
                break
        result["questions"] = questions
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_quiz_generator.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/services/quiz_generator.py tests/test_quiz_generator.py
git commit -m "feat(ml): QuizGenerator.generate — cloze MCQ + AnswerScorer gate"
```

---

## Task 5: Package exports + real-model integration + adapter smoke

**Files:**
- Modify: `ml_pipeline/services/__init__.py`
- Test: `tests/test_generation_integration.py`

**Interfaces:**
- Consumes: `FlashcardGenerator`, `QuizGenerator`, `get_answer_scorer`, real spaCy + real parquet-trained model
- Produces: `ml_pipeline.services` also exports `FlashcardGenerator`, `QuizGenerator`

- [ ] **Step 1: Update `ml_pipeline/services/__init__.py`**

The file currently exports the guidance engines. Add the two generators (keep the existing guidance exports):

```python
"""Service modules for the ML pipeline (guidance + generation)."""
from .flashcard_generator import FlashcardGenerator
from .learning_path import LearningPathEngine
from .quiz_generator import QuizGenerator
from .recommendation_engine import RecommendationEngine

__all__ = [
    "RecommendationEngine",
    "LearningPathEngine",
    "FlashcardGenerator",
    "QuizGenerator",
]
```

- [ ] **Step 2: Write the integration test** `tests/test_generation_integration.py`

```python
"""End-to-end against real spaCy + the real trained AnswerScorer.

Skips cleanly if the model artifact has not been built yet.
"""
import pytest

from ml_pipeline import config
from ml_pipeline.services import FlashcardGenerator, QuizGenerator

_TEXT = (
    "Mitochondria are the powerhouse of the cell, producing energy through respiration. "
    "Ribosomes are responsible for building proteins from amino acids. "
    "The nucleus stores the genetic material of the cell in the form of DNA. "
    "Chloroplasts carry out photosynthesis, converting sunlight into chemical energy. "
    "Photosynthesis occurs in the leaves of green plants and produces oxygen. "
    "The cell membrane controls what enters and leaves the cell."
)


def test_flashcards_have_valid_shape_on_real_text():
    cards = FlashcardGenerator().generate(_TEXT, count=5)
    assert cards, "expected non-empty flashcards on a rich paragraph"
    for c in cards:
        assert set(c) == {"question", "answer", "difficulty"}
        assert c["question"] and c["answer"]
        assert c["difficulty"] in {"easy", "medium", "hard"}


@pytest.mark.skipif(
    not (config.MODELS_DIR / "answer_scorer.joblib").exists(),
    reason="trained answer_scorer.joblib not present",
)
def test_quiz_questions_pass_scorer_gate_on_real_text():
    data = QuizGenerator().generate(_TEXT, question_count=4)
    assert set(data) == {"title", "description", "questions"}
    for q in data["questions"]:
        assert set(q) == {"question_text", "question_type", "options",
                          "correct_answer", "explanation"}
        assert len(q["options"]) == 4
        assert q["correct_answer"] in q["options"]
        assert "______" in q["question_text"]


def test_generation_is_deterministic():
    a = FlashcardGenerator().generate(_TEXT, count=5)
    b = FlashcardGenerator().generate(_TEXT, count=5)
    assert a == b
```

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: ALL pass (generation + guidance + foundation). The quiz integration test runs when the model artifact is present.

- [ ] **Step 4: Verify the Django adapter contract (manual, one-off)**

Confirm the adapter's ML generation path imports and runs (needs Django in the venv; if absent, Step 3 is authoritative):

```bash
cd backend && ../.venv/bin/python -c "import sys; sys.path.insert(0,'..'); from ml_pipeline.services import FlashcardGenerator, QuizGenerator; t='The mitochondria is the powerhouse of the cell. Ribosomes build proteins. The nucleus stores DNA. Chloroplasts do photosynthesis.'; print('cards:', len(FlashcardGenerator().generate(t, 5))); print('quiz qs:', len(QuizGenerator().generate(t, 4)['questions']))"
```
Expected: prints a non-zero `cards:` count and a `quiz qs:` count (0+ depending on the gate) without error.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/services/__init__.py tests/test_generation_integration.py
git commit -m "feat(ml): export generators + real-model generation integration tests"
```

---

## Self-Review

**Spec coverage:**
- §3 contracts (signatures + output keys) → Tasks 2 (flashcards), 4 (quiz); asserted in tests. ✓
- §4 layout (content_extractor + 2 generators, injected deps) → Tasks 1–4; `__init__` exports Task 5. ✓
- §5.1 ContentExtractor (get_nlp memoized, salience, entity/noun-chunk term, dedupe, contiguous span, thin→empty) → Task 1. ✓
- §5.2 flashcards (generic "What is X?" for DEFINITIONAL_LABELS; cloze otherwise) → Task 2. ✓
- §5.3 quiz (cloze stem, distractors same-source/same-label, AnswerScorer gate drops non-#1, shuffle, quality-over-quantity) → Tasks 3, 4. ✓
- §5.4 difficulty (readability buckets) → Task 1 (`difficulty_for`), used in Tasks 2/4. ✓
- §6 data flow / §7 durability (memoized singletons, two-tier failure, deterministic seed, local-only, constants) → Tasks 1/3/4; determinism test Task 5. ✓
- §8 testing (fake scorer/extractor unit tests + real-model integration + determinism + adapter check) → Tasks 1–5. ✓
- §9 acceptance 1–8 → covered across Tasks 1–5 verification. ✓
- §10 out of scope: no generative model, no T/F, no flag flip — none added. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. ✓

**Type consistency:** `Candidate(sentence, term, label, score)`, `ContentExtractor.extract_candidates`, `difficulty_for`, `DEFINITIONAL_LABELS`, `get_nlp`, `FlashcardGenerator(extractor=).generate(text, count, title)`, `QuizGenerator(extractor=, scorer=)._distractors/.generate`, `get_answer_scorer`, and the fixed output dict key sets are consistent across Tasks 1–5 and match spec §3. `scorer.rank(question, candidates, support) -> [(candidate, prob)]` matches `AnswerScorer.rank`. ✓

**Note for implementer:** Task 1's `tests/test_content_extractor.py` and Task 5's integration use **real spaCy**; the generator unit tests (Tasks 2/4) are spaCy-free via `FakeExtractor`, and quiz unit tests are model-free via `FakeScorer`. Task 5 Step 4 needs Django in the venv; Step 3 is the authoritative check otherwise.
