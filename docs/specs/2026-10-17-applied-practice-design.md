# Applied Practice (Bài vận dụng) — Design

**Date:** 2026-10-17
**Status:** Approved in conversation; built before the written review, at the
user's request ("cứ làm hết trước đi rồi tôi sẽ kiểm tra sau").

## Problem

Everything StudyFlow does today trains recall: cards, quizzes, mock tests,
the Feynman check. None of it trains applying what was learned to a problem
the student has not seen. The feature must work for whatever the student
studies (law, programming, economics, languages, sciences), not one subject.

## Decisions taken with the user

1. **Where problems come from: both.** The AI writes problems from a
   document the student uploaded (first), and the student can type in a
   problem of their own (second). Photographed problems are left for later:
   the provider interface takes text only.
   - *Revised 2026-10-19:* own problems belong to **no notebook**. They were
     first filed under one, but graded from general knowledge, so the
     notebook had nothing to do with them. They now live on their own page,
     "Tự luyện" (sidebar, under "Thi thử"), and Progress counts their errors
     on a line of their own.
2. **How work is handed in: submit, with a hint button.** The student writes
   the whole attempt as numbered steps and submits once; "Hint" asks for one
   nudge on the step they are stuck at without submitting.
3. **How a step is judged: against a hidden rubric written with the
   problem.** Each problem is generated with a reference solution, 2–6
   checkpoints an answer must reach, and likely mistakes. Grading checks the
   attempt against the checkpoints, so a different valid route still passes.
   For document problems every checkpoint quotes the document; a checkpoint
   whose quote is not in the text is dropped, and a problem left with fewer
   than two is dropped.
4. **One error vocabulary for every subject**, so Progress can compare:
   `misread` (misread the problem), `concept` (wrong concept or principle),
   `missing_step` (missing step or reasoning), `execution` (slip carrying out
   a step: arithmetic, syntax, wording), `unsupported` (conclusion without
   grounds). Each finding also carries a subject-specific detail sentence.

## Flow

- Notebook → a document → **Make practice problems**: one request writes
  three problems, easy to hard, from the document's main ideas (its key
  points if read, else its text).
- Sidebar → **Tự luyện**: paste a problem on any subject; one request checks
  it is complete enough to solve and writes its rubric from general
  knowledge. Incomplete problems are refused with what is missing. The page
  lists the problems brought so far.
- Problem page: the prompt, step boxes ("+ Add step"), **Hint** (one
  request; a guiding question, never the answer; a hint that repeats the
  reference solution is replaced by one built from the checkpoint), **Submit**
  (one request).
  - All checkpoints reached → passed; the reference solution is shown.
  - Otherwise → the first wrong step, its error type, a hint; the checkpoints
    already reached are ticked. After three failed submits, "Show the model
    solution" unlocks.
- A problem passed on the first submit is **mastered**. One that needed more
  comes back after 3 days (**revisit**).
- Progress gets **Mistakes in practice**: per notebook, counts by error type.

## Data

`exercises` app.

- `Exercise`: user, notebook (null for own problems), source (null for own problems), origin
  (`document` | `own`), prompt, difficulty, reference (JSON: solution steps,
  checkpoints `[{id, text, basis}]`, mistakes), status (`new` | `mastered` |
  `revisit`), revisit_on, created_at.
- `ExerciseAttempt`: exercise, kind (`submit` | `hint`), steps (list of
  strings), result (JSON: verdict, met checkpoint ids, first wrong step, error
  type, detail, hint), created_at.

Problems are private to the student who made them, like mock tests; a
document problem's notebook must be one they can read (`notebooks_for`).

## API (`/api/exercises/`)

| Method | Path | |
|---|---|---|
| GET | `?notebook=&source=` or `?own=1` | list (no rubric) |
| POST | `generate/` `{source_id}` | three problems from a document |
| POST | `own/` `{text}` | the student's own problem, in no notebook |
| GET | `<id>/` | the problem, its attempts; rubric only once passed or unlocked |
| POST | `<id>/submit/` `{steps}` | grade |
| POST | `<id>/hint/` `{steps}` | one hint |
| POST | `<id>/reveal/` | the model solution, after three failed submits |
| GET | `mistakes/` | counts by error type per notebook |

AI requests go through `get_ai_provider()` with `WRITING_STYLE`, the
student's language, and the same quota/busy failure messages as Feynman
feedback; the student's steps are never lost on a failure.

## Measuring the grader

Notebook `ml_pipeline/notebooks/09_step_grading.ipynb` runs the grading
prompt on ProcessBench (Qwen, Apache-2.0): solutions with the index of their
earliest wrong step labelled by experts, which is exactly what Submit
reports. Metrics: accuracy on "is there an error", and exact first-wrong-step
accuracy (ProcessBench's F1 of the two). The free quota allows a small
sample per day; results are cached per item so the sample grows over days.
Other subjects have no public step-labelled set; a small hand-made set
(30–50 problems with a model solution and a few wrong attempts) is the data
the user offered to collect.

## Out of scope

Photographed problems; a per-subject checker (sympy for maths, running code
for programming) as a second opinion; problems shared through a shared
notebook.
