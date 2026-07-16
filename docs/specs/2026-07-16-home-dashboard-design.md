# Home dashboard ("Today") — design

## Problem

The app feels empty, and the emptiness has concrete causes, not a vague one:

- `/dashboard` redirects straight to a bare notebooks list — there is no landing
  screen that greets the user or says what to do now.
- The sidebar has two items (Notebooks, Analytics). Flashcards and quizzes are
  reachable only by going through a notebook with `?source=`.
- The data most capable of making the app feel alive already exists in the
  database but is surfaced nowhere central: the due-card count, per-document
  mastery, recent notebooks, and a study streak.
- `StudyStreak` is fully modelled in the backend (`current_streak`,
  `best_streak`, `update_streak`) yet nothing displays it — and nothing even
  increments it, because its only trigger is ending a `StudySession`, which the
  current review flow never creates.

So the fix is not new subsystems. It is a home screen that surfaces data the app
already produces, plus wiring the one half-built piece (streak) so it runs.

## Scope

A `/dashboard` home page, "Today", assembled from existing endpoints, plus a
minimal backend change to make the streak actually advance. Explicitly **not** in
scope: goals, reminders, sharing, notes, or any new study mode.

## The line between Home and Analytics

They must not duplicate each other.

- **Home** answers *"what do I do right now?"* — the due count with a single
  Study-now action, momentum (streak), and quick re-entry to recent work.
- **Analytics** answers *"how am I doing, and where am I weak?"* — the full
  per-document breakdown and summary stats.

Home may show a weakest-documents glance, but as a shortcut into Analytics, not a
replacement for it (top 2–3, no detail).

## Layout

Five blocks, each backed by data that already exists:

1. **Greeting + streak** — time-of-day greeting; a `🔥 N day streak` chip when
   `current_streak > 0`, otherwise a quiet "Study today to start a streak."
2. **Due today (primary)** — the ready-to-study count with the same breakdown as
   Analytics ("2 overdue · 41 new") and a `Study now →` button to
   `/dashboard/flashcards?due=1`. When nothing is due, the caught-up message with
   the return date, reusing the Analytics logic.
3. **This week** — reviews done and recall accuracy over the last 7 days. This is
   genuinely a week window, so it comes from `card-reviews/stats/`
   (`reviews_this_week`, `accuracy_this_week_percent`), not the all-time summary.
4. **Jump back in** — the most recent notebooks, linking into each.
5. **Weakest right now** — top 2–3 weak documents, each linking to Analytics.

Empty state for a brand-new user (no cards, no notebooks): blocks 2–5 collapse to
a single "Create your first notebook" hero so the page never looks broken.

## Data sources

| Block | Source | Status |
|---|---|---|
| Due count + Study now | `GET /analytics/sessions/recommendations/` (`due`) | exists |
| This week | `GET /api/study/card-reviews/stats/` | exists |
| Recent notebooks | `GET /notebooks/notebooks/` | exists |
| Weakest documents | `recommendations` (`weak_sources`) | exists |
| Streak | `GET /api/study/streaks/me/` | endpoint exists; value needs wiring |

No new read endpoints. `recommendations` and `summary` are already fetched by
Analytics; Home reuses the same client methods, so SWR de-duplicates the calls.

## Streak wiring (the one backend change)

`StudyStreak.update_streak(today)` already does the real work: it extends the
streak on a consecutive day, resets it after a gap, and no-ops on a same-day
repeat. It simply is never called in the review flow.

Fix: call it once whenever a review is recorded, in `CardReview.record` (the
single path both the session-bound and session-less endpoints funnel through).
Because `update_streak` is idempotent within a day, calling it on every review is
safe — the first review of the day advances the streak and the rest are no-ops.

`total_study_minutes` is left untouched and unshown: the review flow does not
track time, and inventing a number would be dishonest. Home shows
`current_streak` (and `best_streak` as a subtitle), nothing more.

The streak day boundary uses `timezone.localdate()`, consistent with the
scheduling fix, so "consecutive day" means the learner's day, not UTC's.

## Navigation

- `/dashboard` renders the Today home instead of redirecting.
- Sidebar gains a **Home** item (top), keeping Notebooks and Analytics. The
  brand mark links to `/dashboard`.

## Testing

- Streak advance is unit-tested at the pure boundary: recording a review on a new
  day increments the streak; a second review the same day does not; a review
  after a gap resets it. (`update_streak` logic already has the day math; the new
  test covers that `record` invokes it.)
- Home is presentational over existing endpoints; no new pure logic beyond the
  streak chip's empty-vs-count wording, which gets a small unit test.

## Out of scope / deferred

- Surfacing flashcards/quizzes as their own nav sections (they remain reached via
  notebooks) — a separate navigation question.
- `total_study_minutes` and any time tracking.
- The `materials` dead route — noted, not addressed here.
