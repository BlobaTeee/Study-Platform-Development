# Mock tests in the shape of a real exam

## Problem

A mock test is currently a longer quiz with a clock: a timed set of multiple-choice
questions, marked out of ten. It measures little that a quiz does not, and it does
not prepare students for the exam's real shape.

## Decision (agreed 2026-11-23, revised the same day)

A sitting is in the exam's shape: numbered parts, each of a different answer kind,
each marked by the real exam's rules.

The student does not pick a format. The first version offered two fixed ones,
"Like the THPT exam" and "45-minute test". The user found the names unrelated and
asked for a random paper instead. Each sitting now draws its own shape
(`template = "mixed"`, `exam.mixed_parts`):

- **Part I.** 8 or 12 multiple-choice questions, 0.25 points each.
- **Part II.** 2 to 4 true/false questions of 4 statements, 1 point each.
- **Part III.** 2, 4 or 6 short answers, 0.5 points each.
- **Part IV.** When Part III does not fill the 10 points, one written problem worth
  what is left.

The time follows the paper's length: 2 minutes per multiple-choice question, 5 per
true/false question, 4 per short answer and 6 per written point. It is rounded up
to 5 minutes and kept between 20 and 120.

The fixed shapes `thpt` and `test45` stay in `exam.TEMPLATES` for the tests, but the
page no longer offers them.

A true/false question earns 0.1, 0.25, 0.5 or 1 of its points for 1, 2, 3 or 4
correct statements, as in the THPT exam.

## Where each part comes from

- **Part I.** The notebook's multiple-choice bank, weighted towards weak documents as
  before. No AI.
- **Part II.** A bank of true/false items (a stem and four statements, each with its
  source passage), new model `TrueFalseItem`. When the bank is short, one AI request
  writes more from the notebook's key points. Each statement must quote its passage.
  The items are kept for later sittings.
- **Part III.** Multiple-choice questions whose answer is short (at most six words),
  asked without their options. They are graded by the existing typed grading: rules,
  then the scorer, then the LLM only for `near`.
- **Part IV.** One practice problem from the notebook's documents, generated if there
  is none. Its prompt and rubric are frozen on the paper. It is graded by the
  practice grader at submit (one AI request), earning its points in proportion to
  the checkpoints met.

## During and after

- During the sitting there is no feedback, as now. The paper is shown part by part.
  True/false is answered with True/False per statement, Part III by typing, Part IV
  in a free-text box.
- After submit the student sees the score out of ten, the points per part, and the
  review of every question with its answer.
- The stored score stays a percentage of the paper's points, so Progress, planned
  tests and the activity calendar keep working unchanged.

## Unchanged

- The classic paper (`template` empty) is still used for the mistakes-only retake
  and for planned tests.
- The mistake bank counts Parts I and III, which are linked to questions. True/false
  items and the written problem are not in it.

## Edge cases

- A notebook without enough short-answer questions gets a shorter Part III. The
  score is a share of the points actually on the paper.
- A true/false or written part that cannot be generated (quota) is left out, and the
  page says so, as a short paper does today.
- A written answer whose grading fails is marked 0 and flagged as "not graded" in the
  review. The sitting is never left unsubmitted.
