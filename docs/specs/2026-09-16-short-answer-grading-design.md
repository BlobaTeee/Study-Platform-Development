# Short-Answer Grading — Design

**Date:** 2026-09-16
**Status:** Approved (design), pending implementation plan
**Author:** pairing session
**Branch:** `feat/short-answer-confidence` (snapshot to revert to: tag `pre-short-answer`)

## Problem

Every quiz question in StudyFlow is multiple-choice. Multiple choice measures
*recognition* — the right answer is on the screen and the student picks it
out. Exams, and durable memory, run on *recall* — a blank line and nothing to
pick from. The testing-effect literature is consistent that producing an
answer beats recognising one, and students know it: they cover the options
and say the answer out loud before looking.

The app cannot grade a typed answer today. It also holds a trained model,
`ml_pipeline.answer_scorer.AnswerScorer` (LogReg over TF-IDF/overlap
features, SciQ, accuracy@1 0.906 on the held-out split), whose only job in
the product is an `if` inside quiz generation. The model exists; nothing the
student can see uses it.

## Goals

- On the Quizzes page, let the student **type an answer** instead of picking
  one, and get a verdict without a cloud call: **correct / near / wrong**,
  with the reference answer shown after grading.
- Grade with the existing `AnswerScorer` plus cheap deterministic checks,
  offline, in milliseconds.
- **Measure before shipping thresholds**: a notebook builds an evaluation
  set from SciQ, reports precision/recall per component and per threshold,
  and the chosen thresholds are recorded with their numbers.
- Record every graded answer, and every time the student overrides the
  verdict, as labelled data the model can later be retrained on.
- Multiple choice stays exactly as it is. Typed mode is a toggle, off by
  default, remembered per browser.

## Non-goals

- Mock tests. They are timed and graded server-side at submission with exact
  matching; typed papers are a later spec once this mode has been used.
- Sentence-length or essay answers. Generated questions have short-phrase
  answers (a term, a name, a number); the grader targets those. A typed
  sentence is graded on the same rules and will often come back *near* —
  the override exists for exactly that case.
- Retraining on the collected labels. This spec collects them; using them is
  the "later spec" `retrain_from_platform.py` already refers to.
- Changing what the scorer is or how it is trained.

## Design

### The grader (`ml_pipeline/services/short_answer.py`, Django-free)

```python
grade(typed: str, reference: str, question: str,
      distractors: list[str], support: str, scorer) -> Verdict
```

`Verdict` is `{"verdict": "correct"|"near"|"wrong", "how": str, "scores": {...}}`
where `how` names the rule that decided (for the UI's "why" line and for the
notebook's per-component breakdown).

Rules, in order — the first that decides wins:

1. **Exact after normalisation.** Lowercase, strip punctuation, collapse
   whitespace, drop a leading article (a/an/the). Equal → `correct`
   (`how = "exact"`). This is most correct answers in practice and costs
   nothing.
2. **Near-string match.** Normalised similarity (token Jaccard, and character
   ratio for one-word answers) ≥ `T_STRING` → `correct` (`how = "string"`).
   Catches plurals, hyphenation, a dropped word in a multi-word answer.
3. **Scorer ranking.** `scorer.rank(question, [typed, reference, *distractors],
   support)`. Let `s_typed`, `s_ref`, `s_dmax` be the probabilities.
   - `s_typed >= s_dmax` and `s_typed >= T_RATIO * s_ref` → `correct`
     (`how = "scorer"`)
   - `s_typed >= s_dmax` → `near`
   - otherwise → `wrong`

   `support` is the question's `explanation` when present (the ML path stores
   the source sentence there; the LLM path writes a one-line explanation
   that restates the fact) and `""` otherwise — with no support the scorer
   falls back to question-overlap and length features, which the notebook
   measures separately.

`T_STRING` and `T_RATIO` are constants in `short_answer.py` **set from the
notebook's numbers**, with the numbers in a comment beside them.

Known blind spot, stated once: a synonym with no shared tokens ("CO₂" for
"carbon dioxide") scores low on every rule. The product answer is the *near*
band plus the override, not a cleverer rule.

### The evaluation (`ml_pipeline/notebooks/04_short_answer_grading.ipynb`)

Built from `datasets/processed/sciq.parquet`, test split only (the scorer
never saw it):

- **Positives** — what a student who knows the answer might type: the
  reference as-is; lowercased/unpunctuated; with/without leading article;
  singular↔plural where a simple rule applies; for multi-word answers, the
  words in a different order and the answer minus one function word.
- **Negatives** — what a student who does not know it types: each of the
  three distractors (the hard case: plausible, on-topic, wrong); one answer
  from a different question (the easy case).

Reported: for each rule alone and for the cascade, precision/recall of
`correct`, and the fraction of positives that land in `near` (the band the
override serves). Sweep `T_STRING` over 0.5–0.9 and `T_RATIO` over 0.5–1.0;
pick the pair that maximises F1 of `correct` subject to precision ≥ 0.9 —
a false "correct" teaches a wrong fact, a false "near" costs one click.
Also report the same table with `support = ""`, since real questions often
have thin explanations. Outputs `ml_pipeline/reports/short_answer_metrics.json`.

The notebook is honest about what it is: synthetic positives are weaker
than real typed answers. The override log is where real labels come from.

### API

`POST /api/quizzes/attempts/{id}/grade_typed_answer/`
`{ "question_id": int, "answer": str }` →

```json
{ "id": 42, "verdict": "near", "how": "scorer", "is_correct": false,
  "reference_answer": "carbon dioxide", "explanation": "..." }
```

Creates the `Answer` row (so `complete` scores the attempt unchanged) with
`is_correct = (verdict == "correct")`. Empty or whitespace-only answer → 400.
Scorer artifact missing → 503 with `detail` naming `ensure_ml_model`;
the frontend hides the typed toggle when it sees a 503 once.

`POST /api/quizzes/attempts/{id}/override_answer/`
`{ "answer_id": int, "is_correct": true }` → flips `is_correct` and
`points_earned` on that row, sets `overridden = true`. Only rows of this
attempt, only typed ones, only before the attempt is completed.

Throttle: none beyond the blanket 60/min — one grade is a few TF-IDF rows.

### Data model (`quizzes.Answer`)

```python
mode = CharField(choices=[('choice', 'Multiple choice'), ('typed', 'Typed')],
                 default='choice')
verdict = CharField(max_length=10, blank=True, default='')   # typed only
graded_how = CharField(max_length=10, blank=True, default='')
overridden = BooleanField(default=False)
```

One migration, all defaults, no data migration. A row with `mode='typed'`
and `overridden=True` is a labelled example: `user_answer` vs the question's
`correct_answer`, label = the student's `is_correct`.

### UI (Quizzes page only)

- A toggle in the quiz header: **Type answers** (off by default; the choice
  is kept in `localStorage`). Switching mid-quiz is allowed; the current
  question re-renders in the new mode, previous answers are untouched.
- Typed mode replaces the option list with one input, `Check` (Enter), and
  after grading:
  - **correct** — green check, "Correct", the reference under it.
  - **near** — amber, "Close — the answer is *X*", and a small
    **I was right** button that calls override; on success the badge turns
    green and the score increments.
  - **wrong** — red, "Not quite — the answer is *X*", the same override
    button, smaller.
  - The explanation shows under the reference, as it does today.
- Keyboard: Enter checks, Enter again advances, `r` overrides when offered.
- No AI sparkle. The verdict line is text; the "how" is not shown to the
  student (it goes to the notebook), except a muted "graded offline" the
  first time typed mode is used.

### Error handling

- Grader exception (scorer load, feature transform) → 503, logged once per
  process; the client shows "Typed grading isn't available right now" and
  switches the question back to choices.
- Override on a completed attempt → 400; on a choice-mode row → 400.
- `T_*` constants missing from the notebook run → the module has literal
  defaults; the notebook writes new values only into its report, and a
  human copies them into the constants with the numbers beside them.

## Testing

- **Pure (`tests/`)**: `grade` with a stub scorer — exact after
  normalisation; article/plural/order handled by the string rule; scorer
  branch yields `correct` / `near` / `wrong` for controlled probabilities;
  empty typed answer never reaches the scorer.
- **Notebook**: the metrics file exists and contains the chosen thresholds;
  the constants in `short_answer.py` equal them (a pure test reads both).
- **API (`backend/tests`)**: grade creates a typed `Answer` and returns the
  reference; override flips the row and is refused after completion and on
  choice rows; a missing scorer artifact → 503 (monkeypatched loader);
  `complete` counts overridden answers as correct.
- **Manual**: on `/dashboard/quizzes?source=…`, toggle Type answers, type a
  right answer, a plural, a distractor; override a near.

## Out of scope, noted for later

- Mock tests in typed mode (server-side grading at submit, review shows the
  verdict per question).
- Using the override log to retrain — `retrain_from_platform.py` is the
  entry point, and `Answer(mode='typed')` rows are the data.
- Provenance (idea 1 of the previous list) would give the grader a real
  `support` passage instead of the explanation; it stacks on this.
