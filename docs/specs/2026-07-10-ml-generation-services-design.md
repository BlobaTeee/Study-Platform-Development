# ML Generation Services — Design Spec

**Status:** Approved (brainstorming) — ready for implementation planning
**Date:** 2026-07-10
**Depends on:** `2026-07-03-ml-foundation-design.md` (the trained `AnswerScorer`), spaCy `en_core_web_sm`

## 1. Goal

Implement the two **Generation** modules under `ml_pipeline/services/` that the Django
adapter ([`backend/ml/adapter.py`](../../../backend/ml/adapter.py)) already imports but that
do not yet exist:

- `ml_pipeline/services/flashcard_generator.py` → `FlashcardGenerator`
- `ml_pipeline/services/quiz_generator.py` → `QuizGenerator`

plus one shared internal module they both build on:

- `ml_pipeline/services/content_extractor.py` → `ContentExtractor` + `get_nlp()`

These turn a student's own source text into flashcards and quizzes using **classical,
local** NLP (spaCy + scikit-learn TF-IDF), with the trained `AnswerScorer` as a quality
gate on quiz questions. When built, they power the ML path in
[`generate.py`](../../../backend/notebooks/services/generate.py) (gated by `USE_ML_PRIMARY`)
and the offline/quota fallback in [`fallback.py`](../../../backend/notebooks/services/fallback.py).

## 2. Context, intent & constraints

1. **Intent: ML becomes the primary generator.** Gemini is temporary scaffolding for the
   demo; the trained ML is meant to replace it. This subsystem is the first step toward
   that. It is built to be promotable to primary (flip `USE_ML_PRIMARY=True`) and is
   *also* the offline/quota fallback today.
2. **Honest quality ceiling.** Classical extraction (spaCy + TF-IDF + AnswerScorer) reads
   more mechanically than an LLM. Truly LLM-level generation would need a trained
   generative model — a later spec, explicitly out of scope here (§10).
3. **Question style: cloze + definitional mix** (approved). Quizzes use fill-in-the-blank
   (cloze) MCQs; flashcards use definitional Q&A with a cloze fallback.
4. **Quality over quantity** (approved). Return only validated items, up to the requested
   count; never pad with weak/unvalidated questions. Return empty if nothing valid can be
   made (the adapter then falls back).
5. **Classical + local only** — spaCy, scikit-learn TF-IDF, joblib. No LLM, no network.
6. **`ml_pipeline` stays framework-free.** No Django imports. Generators take plain `text`
   and return plain dict/list structures the adapter maps onto Django models.
7. **Signatures fixed** by the adapter; **output keys fixed** by the Django model mapping
   in the adapter and the quiz save loop in `generate.py`.

## 3. Integration contract (fixed — do not change)

```python
FlashcardGenerator().generate(text: str, count: int, title: str) -> list[dict]
# each dict: {"question": str, "answer": str, "difficulty": "easy|medium|hard"}

QuizGenerator().generate(text: str, question_count: int, title: str) -> dict
# {"title": str, "description": str,
#  "questions": [{"question_text": str, "question_type": "multiple_choice",
#                 "options": list[str], "correct_answer": str, "explanation": str}]}
```

The adapter reads `item["question"]`, `item["answer"]`, `item.get("difficulty","medium")`
for flashcards; and `data["title"]`, `data.get("description")`, `data.get("questions")`,
then per question `q["question_text"]`, `q.get("question_type","multiple_choice")`,
`q.get("options",[])`, `q["correct_answer"]`, `q.get("explanation")`.

## 4. Architecture & module layout

```
ml_pipeline/services/
├── content_extractor.py    # shared spine: get_nlp() + ContentExtractor
├── flashcard_generator.py  # FlashcardGenerator (adapter-facing)
└── quiz_generator.py        # QuizGenerator + distractor generation + get_answer_scorer()
```

Both generators accept injected dependencies and fall back to memoized singletons in
production (the guidance-subsystem pattern):
`FlashcardGenerator(extractor=None)`, `QuizGenerator(extractor=None, scorer=None)`.

## 5. Component design

### 5.1 ContentExtractor (`content_extractor.py`)

- `get_nlp()` — memoized spaCy `en_core_web_sm` (loaded once per process; raises if the
  model is unavailable).
- `@dataclass(frozen=True) Candidate(sentence: str, term: str, label: str, score: float)`
  — `sentence` is the support/context, `term` is the answer span, `label` is the spaCy
  entity type or `"NOUN_CHUNK"`, `score` is salience.
- `ContentExtractor.extract_candidates(text: str, max_candidates: int) -> list[Candidate]`:
  1. Segment `text` into sentences (spaCy). Defensive length cap on `text`.
  2. Filter sentences by length bounds (`MIN_SENT_TOKENS`..`MAX_SENT_TOKENS`); keep only
     those containing an extractable key term.
  3. Salience: fit TF-IDF over the document's own sentences; a sentence's score is the
     summed TF-IDF weight of its terms. Rank descending.
  4. Key term per sentence: prefer spaCy named entities with an answerable label
     (`ANSWERABLE_ENT_LABELS`); else the highest-TF-IDF noun chunk. The term must be a
     contiguous span in the sentence (so it can be blanked / asked about).
  5. Dedupe by lowercased term; return the top `max_candidates`, stable-sorted by
     `(-score, sentence)`.
  - Thin/termless text → `[]` (never raises for content reasons).

### 5.2 FlashcardGenerator (`flashcard_generator.py`)

`generate(text, count, title) -> list[dict]`:
1. `candidates = extractor.extract_candidates(text, count * OVERSAMPLE)`.
2. Per candidate, choose the card style from the candidate's `label` (deterministic):
   - **Definitional** when `label` is a named-entity type (an answerable entity):
     stem by label — `PERSON → "Who is {term}?"`, `GPE/LOC → "What is {term}?"`,
     `DATE/EVENT → "What happened: {term}?"`, default `"What is {term}?"`; `answer` = the
     support sentence.
   - **Cloze** when `label == "NOUN_CHUNK"` (common-noun terms, where "What is {term}?"
     usually reads awkwardly): `question` = the support sentence with the term replaced by
     `"______"`, `answer` = the term.
3. Attach `difficulty` (§5.4).
4. Dedupe by answer/term; take up to `count`. Fewer candidates → fewer cards; none → `[]`.
   Output rows exactly `{question, answer, difficulty}`.
- No AnswerScorer (no correct-vs-distractor decision exists for flashcards).

### 5.3 QuizGenerator (`quiz_generator.py`)

- `get_answer_scorer()` — memoized `AnswerScorer.load(config.MODELS_DIR / "answer_scorer.joblib")`
  (raises if the artifact is missing/corrupt).
- `generate(text, question_count, title) -> dict`. Per candidate, build a cloze MCQ:
  1. Stem = support sentence with the term blanked (`"______"`); `correct_answer` = term.
  2. Distractors (need `N_DISTRACTORS = 3`): pool = other candidate terms from the **same
     source**, preferring the **same entity label**; rank by TF-IDF similarity to the
     correct term (tempting, not synonymous); take distinct top candidates. If fewer than
     `N_DISTRACTORS` are available, **skip this question**.
  3. **AnswerScorer gate**: `options = [correct] + distractors`;
     `ranked = scorer.rank(stem, options, support=sentence)`. If `ranked[0]` is not the
     correct answer, **drop the question**. Prefer distractors the scorer rates
     high-but-below-correct (hardest valid) when choosing among a larger pool.
  4. Assemble: `question_type="multiple_choice"`; `options` = the four shuffled
     deterministically (seeded); `explanation` = support sentence.
- Keep up to `question_count` validated questions; fewer valid → fewer; none →
  `questions: []`. `description = f"Generated from {title}"`.

### 5.4 Difficulty (shared heuristic)

Per item, combine: answer-term rarity (IDF/TF-IDF weight — rarer → harder) and support
readability (`textstat.flesch_reading_ease` — lower → harder). Bucket into
`{easy, medium, hard}` via named thresholds. Transparent heuristic, not a predictor.

## 6. Data flow

```
generate.py (_use_ml_primary) / fallback.py
  → ml.adapter.generate_flashcards_ml / generate_quiz_ml
    → FlashcardGenerator / QuizGenerator
      → ContentExtractor (get_nlp)  [+ QuizGenerator: get_answer_scorer]
    ← list[dict] / {title, description, questions} matching §3
```

## 7. Error handling & durability

- **Memoized singletons:** `get_nlp()` and `get_answer_scorer()` load once per process.
- **Two-tier failures:** thin/termless text or over-strict gate → fewer / empty → adapter
  falls back (normal). Genuine load failure (spaCy model or `answer_scorer.joblib`
  missing/corrupt) → raises → adapter `try/except` → Gemini/crude fallback.
- **Deterministic:** seeded option shuffles (`config.RANDOM_SEED`); stable tie-broken
  sorts; same input → same output.
- **Local only:** no network/LLM. Defensive text-length cap.
- Tunables (`OVERSAMPLE`, difficulty thresholds, `N_DISTRACTORS`, sentence-length bounds,
  `ANSWERABLE_ENT_LABELS`) as named constants at module tops.

## 8. Testing (TDD)

- **Unit tests**, tiny text fixtures. QuizGenerator tests inject a **fake AnswerScorer**
  (deterministic `.rank()`) to exercise both the accept and drop paths without the trained
  model.
  - `ContentExtractor`: extracts the expected term; salience ranks the key sentence first;
    dedupe; thin/termless → `[]`.
  - `FlashcardGenerator`: definitional shape; cloze fallback; count respected;
    fewer-when-thin; exact keys; difficulty ∈ {easy,medium,hard}.
  - `QuizGenerator`: 4 options incl. correct; distractors from the source; fake scorer
    ranks correct #1 → kept, ranks it lower → dropped; quality-over-quantity; exact keys;
    `question_type="multiple_choice"`; `explanation` = support.
- **Real-model integration test**: `get_answer_scorer()` (real `answer_scorer.joblib`) +
  real spaCy on a real paragraph → valid MCQs where the correct answer ranks #1. Skips if
  the artifact is absent.
- **Determinism test**: same input twice → identical output.
- **Adapter contract check**: `from ml.adapter import generate_flashcards_ml, generate_quiz_ml`
  import path resolves (Django-dependent; noted like the foundation's Task 12).

## 9. Acceptance criteria

1. The three modules exist; `ContentExtractor`, `FlashcardGenerator`, `QuizGenerator` and
   the memoized `get_nlp()` / `get_answer_scorer()` are importable.
2. Generators satisfy §3 signatures and output shapes exactly.
3. Flashcards: definitional-first with cloze fallback; exact keys; difficulty in-set.
4. Quizzes: cloze MCQ with 4 options; every emitted question passes the AnswerScorer gate
   (correct answer ranks #1); distractors are same-source.
5. Quality over quantity: thin sources yield fewer items; nothing valid → empty; never pad.
6. Generators return empty on content reasons and raise only on genuine load failure.
7. Deterministic output for a fixed input.
8. Full test suite passes, including the real-model integration test (when the artifact is
   present).

## 10. Out of scope / future

- **Trained generative model** for LLM-level fluency (the real path to fully replacing
  Gemini) — its own spec.
- **True/false and short-answer** question types (v1 is cloze MCQ only).
- **Flipping `USE_ML_PRIMARY`** to make ML primary in production — a deployment decision
  once quality is judged sufficient.
- **AnswerScorer retraining** from platform feedback (`retrain_all` using `platform_cards`).
