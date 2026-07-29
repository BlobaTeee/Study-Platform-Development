# Mock Tests — Design

**Date:** 2026-07-25
**Status:** Approved (design), pending implementation plan
**Author:** pairing session

## Problem

StudyFlow can drill a student on individual documents, but it cannot answer the
question that actually matters before an exam: *"if I sat a paper on this
subject right now, how would I do?"* Quizzes are per-document, untimed, and give
feedback after every question, so they measure recognition under ideal
conditions rather than recall under exam conditions.

Two gaps follow from that:

1. **No exam-condition practice.** `Quiz.time_limit` exists on the model but is
   never used — nothing in the interface or the API enforces it, and feedback is
   immediate, so a quiz cannot be sat as a test.
2. **No way to commit to studying later.** A student who decides on Monday to
   sit a Biology paper on Friday has nowhere to record that, and nothing
   reminds them.

## Goals

- **Take a mock test now:** a timed paper drawn from across a whole notebook,
  with feedback withheld until submission.
- **Plan a test for later:** record subject, time, length, and receive a
  **reminder email** at a lead time of the student's choosing.
- Reuse the material the student has already generated — no new model calls to
  start a test.

## Non-goals

- Changing the existing quiz flow (`start_attempt` / `submit_answer` /
  `complete`) or its models.
- Generating new questions at test time.
- Multi-user proctoring, or any anti-cheating beyond a server-authoritative
  clock.

## Constraints

- **No task queue.** Reminders must be sent by something external to the request
  cycle; the project has no Celery or RQ, and adding one is out of proportion to
  the feature.
- **No email configuration exists** in the project today.
- Local machine (M2 / 8 GB): starting a test must be fast, which rules out
  generating a paper on demand.

## Decisions

Settled during brainstorming:

| Question | Decision |
|---|---|
| What a paper is made of | **Sampled across a notebook's existing questions**, weighted toward weak topics |
| When questions are chosen | At **sitting** time, not planning time |
| Reminder delivery | **Django management command** run by cron/launchd — no worker process |
| Reminder timing | **Chosen when planning** — 1 hour / 1 day / 3 days, default 1 day |
| Email transport | **Real SMTP**, credentials from `backend/.env` |

Rejected: assembling a paper by generating fresh questions with the local LLM
(slow to start a test, and needs a fallback before the student can begin);
Celery with Redis (heavy for a single-machine project).

## Components

### 1. Data model

Three new models in the `quizzes` app. Existing quiz models are **not** touched.

**`MockTest`** — one sitting.

| Field | Notes |
|---|---|
| `user`, `notebook` | FKs |
| `question_count`, `duration_minutes` | Chosen when the test is created |
| `started_at` | Set when the paper is frozen; the clock starts here |
| `completed_at`, `score` | Set on submission; score is percent correct |

**`MockTestQuestion`** — the frozen paper, and the student's answers.

| Field | Notes |
|---|---|
| `mock_test`, `question` | FK to the existing `quizzes.Question` |
| `order` | Fixed at freeze time |
| `user_answer`, `is_correct`, `answered_at` | Nullable until answered |

**`PlannedTest`** — the intention, and the reminder's state.

| Field | Notes |
|---|---|
| `user`, `notebook` | FKs |
| `scheduled_for` | Datetime; must be in the future |
| `question_count`, `duration_minutes` | Carried into the sitting |
| `reminder_lead_hours` | `1`, `24`, or `72`; default `24` |
| `reminder_sent_at` | Null until sent — the idempotency guard |
| `mock_test` | Nullable FK, set when the plan is actually sat |

`QuizAttempt` and `Answer` are deliberately not reused: both are tied to a
single `Quiz` by a non-null FK, and a mock test spans many quizzes. Storing the
answer on `MockTestQuestion` duplicates a little of `Answer`, and buys back both
a frozen paper (a refresh cannot reshuffle questions mid-test) and zero
migration risk to the working quiz flow.

### 2. Paper assembly — `backend/quizzes/services/paper.py` (new)

```python
sample_paper(pool, weights, count, seed) -> list[Question]
```

A **pure function**: it receives the candidate questions and their weights and
returns the chosen paper, so it is unit-testable without a database.

- **Pool.** Every `Question` whose `Quiz` belongs to the notebook's sources.
  Quizzes carry their source tag in `description`, so the pool is resolved with
  the existing `combined_source_tag` helper rather than a new association.
- **Weighting.** Topics the student has scored poorly on are drawn more often,
  reusing accuracy already computed in `analytics.insights`. Weighting raises
  the probability of weak material appearing; it never guarantees it, so a paper
  stays varied between sittings.
- **Timing.** Sampling happens when the test is *started*, so a paper planned
  three days ahead includes anything generated in the meantime.

### 3. Taking a test

Both modes converge on one flow:

```
start   → resolve pool → sample_paper() → freeze MockTestQuestion rows
        → stamp started_at (the clock starts server-side)
answer  → record user_answer; NO correctness returned
submit  → grade every row, compute score, stamp completed_at
        → return the full per-question review
```

- **The deadline is server-authoritative:** `started_at + duration_minutes`. The
  client renders a countdown, but a client-only timer is bypassed by editing the
  page, so the server rejects answers after the deadline and the submit endpoint
  grades whatever was recorded.
- **Feedback is withheld until submission.** This is the whole difference
  between a test and a quiz; `submit_answer` on a mock test must not leak
  `is_correct` in its response.
- An abandoned test (deadline passed, never submitted) is auto-submitted on next
  access with the answers it has.

### 4. Planned tests and the reminder

New management command: `backend/quizzes/management/commands/send_test_reminders.py`.

Selection is extracted as a pure function so it is testable without email, cron,
or a clock:

```python
due_reminders(plans, now) -> list[PlannedTest]
```

A plan is due when `scheduled_for - reminder_lead_hours <= now`, its
`reminder_sent_at` is null, and it has not already been sat. The command sends
each reminder and stamps `reminder_sent_at` immediately, which makes it
**idempotent** — safe to run every fifteen minutes, and incapable of sending
twice.

The email states the subject, the scheduled time, and the paper's length, and
links to the test.

**Scheduling it** is an operational step, not code: one cron (or launchd) entry
running the command periodically. The command is the unit under test; the
scheduler is only a trigger, and the design is deliberately indifferent to which
one is used. It only fires while the machine is awake — acceptable for a
single-machine project, and worth stating plainly rather than discovering during
a demo.

### 5. Email configuration

Settings read from the environment via `python-decouple`, matching how the
project already configures Supabase and the AI provider:

`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
`EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`.

Keys are added to `.env.example` **with empty values**. The credential must be a
provider app password rather than an account password, and `backend/.env` is
already gitignored. Tests use Django's `locmem` backend and never touch the
network.

## Error handling

- **Pool smaller than the requested count** → build the paper from what exists
  and tell the student the paper is short. An **empty pool** is a clear message
  ("generate some quizzes for this notebook first"), not an error page.
- **Planning a test in the past** → validation error on the serializer.
- **SMTP failure** → log it and leave `reminder_sent_at` null so the next run
  retries; one failing recipient must not abort the whole batch.
- **Answer submitted after the deadline** → rejected with the test's final state
  rather than silently accepted.
- **Starting a test twice** → the existing sitting is returned rather than a
  second paper frozen.

## Testing

- **Sampling:** respects `count`; weights weak topics upward; handles a pool
  smaller than `count`; is deterministic under a fixed seed.
- **Reminders:** `due_reminders` selects a plan exactly at its lead-time
  boundary, skips one already sent, skips one already sat, and skips one still
  in the future; re-running the command sends nothing the second time.
- **Timer:** an answer after `started_at + duration` is rejected; an abandoned
  test auto-submits with partial answers.
- **Feedback withholding:** the answer endpoint's response contains no
  correctness field.
- **Scoring:** percent correct matches the existing quiz convention.
- **Email:** subject, recipient, and body asserted against the `locmem` backend.

## Relationship to other work

Independent of the flashcard review-quality spec
(`2026-07-25-flashcard-review-quality-design.md`); the two share no models and
can be built in either order. This one reads `analytics.insights` for weak-topic
weighting, which that spec does not modify.
