# Analytics Revamp — Practical Insights From Real User Data

**Date:** 2026-07-16
**Status:** Approved (design), pending implementation
**Author:** pairing session

## Problem

The analytics page shows a lot that is either irrelevant or unused.

**Recommendations and Learning Path are built on a fixed 5-subject STEM taxonomy**
(Computer Science, Chemistry, Biology, Physics, Mathematics) derived from the
AI Flashcards dataset. Real uploaded documents rarely fall in those subjects, so
the features cannot be relevant. Measured against the user's real data:

- Document: *"Cognitive Impact on App Design"* (HCI / accessibility for homeless
  food access). Recommendation returned: **Biology · Ecology · Food Webs** — a
  bare keyword collision on "food".
- Learning Path returned **Data Structures · Graphs**, **NP-Completeness**,
  **Synchronization** — unrelated to anything the user studies, because with 0
  completed quiz attempts there is no performance signal to personalise with.

This is a data-foundation problem, not a layout problem: no redesign of the
taxonomy-backed features can make them relevant.

**Manual study-session logging** (a form for typing in minutes studied) is a
chore users skip, and the "Recent study sessions" list only has meaning if that
form is used.

Meanwhile the app already holds genuinely useful, real data that is barely
surfaced: per-flashcard `correct_count` / `incorrect_count`, and `tags`
(`source:N`) linking every card back to the document it came from.

## Goal

An analytics page where every element is real, correct, and actionable —
answering "what should I review next, and where am I weak?" from the user's own
performance.

Non-goals: full spaced-repetition scheduling (SM-2), new DB fields/migrations,
changes to generation, resurrecting the taxonomy.

## Decisions

| Element | Decision |
|---|---|
| Study Recommendations | **Rebuild** from the user's own cards/performance |
| Adaptive Learning Path | **Remove** from the product surface |
| Log a study session (manual form) | **Remove** |
| Recent study sessions | **Remove** |
| Summary stats | **Keep, trimmed** |
| Flashcard reviews | **Keep** |

Because manual logging goes, `total_study_minutes` and `study_sessions_count`
become meaningless and are dropped from the summary too.

## Design — three blocks, all actionable

1. **"What to review next"** (primary block)
   Top ~5 highest-priority cards, with a link into review.
2. **"Where you're weakest"**
   Per-document accuracy: each real source title, its accuracy, and card count.
   Derived by parsing `tags` (`source:N`) back to `Source.title`.
3. **Summary (trimmed) + Flashcard reviews**
   Flashcard accuracy, average quiz score, total cards, total reviews.

### Priority score

Laplace-smoothed error rate per card:

```
priority = (incorrect + 1) / (correct + incorrect + 2)
```

Ranked descending. This handles all three cases sensibly with one formula:
- low accuracy → high priority
- never reviewed → 0.5 (middle: unknown mastery, worth testing)
- consistently correct → low priority

### Per-document accuracy

A card's `tags` holds `source:1,2` (a card may come from several sources).
Accuracy for a document = summed correct / summed reviews across cards tagged
with that source id. Documents with zero reviews are reported as "not reviewed
yet" rather than 0%.

## Components

- **`backend/analytics/insights.py`** (new, pure, no Django imports):
  - `card_priority(correct, incorrect) -> float`
  - `rank_weak_cards(cards, limit) -> list`
  - `parse_source_ids(tag) -> list[int]`
  - `per_source_accuracy(cards, source_titles) -> list`
  Views feed it ORM data; the module stays unit-testable in isolation, the same
  pattern as `quiz_shaping.py` / `source_guard.py`.
- **`backend/analytics/views.py`**:
  - `recommendations` — rewritten to use `insights` over the user's own cards
  - `learning_path`, `subjects` — removed
  - `summary` — drop `total_study_minutes`, `study_sessions_count`
  - StudySession CRUD — removed from the API surface
- **`app/dashboard/analytics/page.tsx`** — rewritten to the three blocks.
  Currently 450 lines; the result should be materially smaller and simpler.

## What is intentionally left alone

`RecommendationEngine`, `LearningPathEngine` and `TopicIndex` stay in
`ml_pipeline` with their tests. They are unwired from the product but remain a
legitimate record of the ML exploration for the FYP write-up. The `StudySession`
model stays (no destructive migration); only its UI/API surface is removed.

**Honest consequence:** with these unwired, the AI Flashcards dataset has no
remaining consumer in the product. Given it is templated boilerplate (179
distinct answers across 67,957 rows), that is the correct outcome, but it should
be stated plainly rather than hidden.

## Testing

- **TDD** the pure `insights` functions: priority ordering, never-reviewed
  cards land mid-priority, multi-source tag parsing, malformed/empty tags,
  per-document aggregation, zero-review documents.
- Verify endpoints against the real user's data (10 flashcards, 1 quiz) and
  confirm the page renders real document titles rather than taxonomy subjects.

## Success criteria

Every element on the page is derived from the user's own activity and is
correct: no "Food Webs" for an HCI document, no NP-Completeness path, no dead
manual-entry form. The primary block tells the user which of *their* cards to
review next, and the second names which of *their* documents they are weakest on.
