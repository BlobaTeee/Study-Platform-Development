# Flashcard Review Quality — Design

**Date:** 2026-07-25
**Status:** Approved (design), pending implementation plan
**Author:** pairing session

## Problem

Three defects in the flashcard review loop, all of which push the student
toward memorising strings instead of learning material.

1. **Failed cards return identical.** Grading a card *Hard* schedules the same
   `Flashcard` row to reappear. The student who could not answer
   "What is photosynthesis?" is shown that exact wording again, and eventually
   recalls the string rather than the concept. Re-study stops testing anything.
2. **Generation stacks without limit.** Each press of *Generate* appends up to
   ten new cards to the same source. `dedupe.new_flashcards` rejects only
   *identical* questions, so three presses leave roughly thirty cards for one
   document. Nothing caps the total.
3. **Four grades, two of them ambiguous.** *Again* and *Hard* both mean "that
   went badly", and choosing between them is friction mid-session.

## Goals

- A card graded *Hard* comes back as a **different question on the same
  concept**, so re-study tests understanding.
- A document holds **at most ten active cards**, however many times generation
  runs.
- **Three grades** — Hard / Good / Easy — with *Hard* carrying the
  reset-to-day-one behaviour that *Again* used to.

## Non-goals

- Changing quiz generation, the Ollama provider, or the extractive ML pipeline.
- Editing or rejecting cards by hand (a separate, larger feature).
- Any change to how `rank_due_cards` orders the queue.

## Constraints

- **No background-task infrastructure.** No Celery, RQ, or threads; generation
  is synchronous today. The design must not require a worker.
- **A model call costs ~6s** on the target machine (M2 / 8 GB), so it must never
  block grading mid-session.
- **Cloud-free.** Regeneration uses the configured local provider and falls back
  to deterministic reformatting — never to Gemini.

## Decisions

Settled during brainstorming:

| Question | Decision |
|---|---|
| What varies in a variant | A **new question on the same concept** — may test a different facet, and may have a different answer |
| Fate of the original | **Replaced** — archived, and the variant inherits its schedule |
| When regeneration runs | **Lazily, at due-fetch time** (Approach A) |
| Cap behaviour | **Top up to ten** — never delete or exceed |
| Grade scale | **Hard / Good / Easy**, with *Hard* resetting to day one |

Approaches rejected: generating in a background thread at grade-time (Django's
dev server handles threads poorly, and *Hard* cards return the same day, so the
thread often would not finish first), and generating synchronously at
grade-time (~6s pause after every *Hard* press).

## Components

### 1. Three-grade scale

`backend/study_sessions/scheduling.py`

- Drop the `AGAIN` constant; `RESULT_VALUES` becomes `(HARD, GOOD, EASY)`.
- `HARD` takes over the old `AGAIN` body — `Schedule(1, max(MIN_EASE_FACTOR,
  ease_factor - 0.2), 0)` — so a failed card returns tomorrow with its
  repetition count reset. Without this, no grade would reset a card and
  forgotten material would drift steadily further away.
- `CORRECT_RESULTS` stays `{GOOD, EASY}`; accuracy reporting is unchanged.

`CardReview.RESULT_CHOICES` drops `again`. **No data migration is needed for
historical rows:** `again` and `hard` both count as incorrect in
`analytics.insights`, and `CardReview.record` carries forward
`interval`/`ease_factor`/`repetitions` rather than replaying the stored grade,
so old rows are never passed back into `next_schedule`.

Frontend: remove the `again` entry from the `GRADES` array in
`app/dashboard/flashcards/page.tsx`. The number-key shortcuts renumber to 1–3.

### 2. Data model

`Flashcard` gains four fields:

| Field | Type | Purpose |
|---|---|---|
| `origin` | self-FK, nullable, `on_delete=SET_NULL` | The card this was regenerated from |
| `archived` | bool, default `False` | Retired; excluded from every study queue |
| `needs_regeneration` | bool, default `False` | Set when graded *Hard*; cleared on replacement |
| `generation` | int, default `0` | How many times this concept has been regenerated |

`CardReview` gains one field:

| Field | Type | Purpose |
|---|---|---|
| `is_seed` | bool, default `False` | A schedule-carrying row that hands a variant its parent's SM-2 state |

Seed rows are counted for scheduling and **excluded from accuracy analytics** —
they record no actual recall.

### 3. Variant generator

New, isolated unit: `backend/flashcards/services/variant_generator.py`,
exposing `generate_variant(card) -> dict | None`. The provider is injected so
the unit is testable without a running model.

- **Anchor.** The card's own question and answer identify the concept; the
  source excerpt (resolved from `card.tags` → source ids → `extracted_text`)
  grounds the model so it cannot drift or invent material.
- **Prompt.** Asks for exactly one flashcard testing the same underlying
  concept from a different angle, answerable from the excerpt alone, returned
  as JSON.
- **Dedupe.** Reuses the existing content-hash in `notebooks/services/dedupe.py`
  to reject a variant too close to the original, then retries once more
  strictly.
- **Fallback chain.** Local model → deterministic reformat of the original
  (cloze via `content_extractor.blank_term`, or a question/answer flip) →
  `None`, meaning keep the original this round and try again next time.

### 4. Deck cap

`backend/notebooks/services/generate.py`

- New constant `MAX_CARDS_PER_SOURCE = 10`.
- Before generating, count the **active** (non-archived) cards carrying this
  source tag: `room = MAX_CARDS_PER_SOURCE - existing`. Request at most `room`
  cards; if `room <= 0`, generate nothing and report that the document is full.
- `_save_flashcards_from_json` enforces `room` as a hard ceiling, so a model
  that over-produces still cannot push the document past ten. This matters
  because the existing `count = max(3, min(count, 20))` clamp would otherwise
  raise a request for one or two remaining slots back up to three: asking for
  more than `room` is harmless, saving more than `room` is not, so the ceiling
  lives at the save step.
- The cap counts active cards only, which is what makes the two features agree:
  a variant archives one card and adds one, so refreshing a hard card leaves the
  document at ten rather than eleven.
- Scope note: the cap applies per **source selection** — the existing `tags`
  grouping — so generating from a single document caps that document at ten.

Frontend: `material_counts` already returns the count, so the generate button
reads "Generate (7/10)" and becomes a disabled "Full" at ten.

### 5. Flow

```
Grade "Hard"
  → CardReview.record() sets card.needs_regeneration = True
    (instant; no model call, so grading never stalls)

Next due-cards fetch
  → for each DUE card with needs_regeneration:
       generate_variant(card)
         success → create variant V (origin=card, tags copied, generation+1)
                   archive the original, clear its flag
                   seed V with an is_seed CardReview carrying the parent's
                   interval / ease_factor / repetitions / next_review_date
                   → V is due exactly when the original was
         failure → leave the original in place, keep the flag, retry next fetch
  → return the batch with each variant swapped in for its original
```

Archived cards are filtered out of every study queue, so a concept has exactly
one active card and the memorised wording never reappears. The frontend needs no
structural change — variants arrive through the existing due-cards path — beyond
an optional quiet provenance line ("a new take on a card you found hard").

## Error handling

- **At-limit generation** is a calm no-op with a message, never an error. A
  partial top-up (fewer cards than `room` survive dedupe) is a success.
- **Provider unavailable or invalid JSON** → deterministic reformat → keep the
  original. Studying is never blocked by a failed regeneration.
- **Variant too similar** → dedupe rejects it → one stricter retry → fallback.
- **Missing or empty source text** → anchor on the question and answer alone.
- **Slow fetch.** Regenerations per due-fetch are capped so a large backlog
  cannot stall the request; the page shows a brief "Preparing your review…"
  state. The model's `keep_alive` already holds it resident between calls.

## Testing

Scheduling and the cap are pure functions and stay unit-testable without a
database, matching `tests/test_spaced_repetition.py`.

- **Grades:** `next_schedule("hard", ...)` resets interval to 1 and repetitions
  to 0 and lowers ease; `RESULT_VALUES` rejects `"again"`; `CORRECT_RESULTS` is
  unchanged.
- **Cap:** generating into a document with six cards adds exactly four;
  generating at ten adds none and reports full; archived cards do not count
  toward the cap; a model returning twenty cards still saves at most `room`.
- **Variants:** `generate_variant` returns a question distinct from the original
  (fake provider); dedupe rejection triggers the retry, then the reformat
  fallback; a raising provider yields `None` and leaves the card untouched.
- **Flow:** grading *Hard* sets `needs_regeneration`; the due-fetch swaps in the
  variant and archives the original; the seeded schedule makes the variant due
  on the parent's date; `is_seed` rows do not move reported accuracy.

## Follow-up (separate spec)

Mock tests — a take-now timed test and a planned test with a reminder email —
are deliberately out of scope here. That work extends the existing `quizzes`
models (`Quiz` already carries `time_limit`) and needs two things this project
does not yet have: email configuration, and something that runs at a scheduled
time to send the reminder. It gets its own design.
