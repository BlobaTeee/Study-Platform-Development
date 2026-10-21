# Knowledge Map (Bản đồ kiến thức) — Design

**Date:** 2026-10-20
**Status:** Approved in conversation, section by section; awaiting review of this document.

## Problem

StudyFlow has eight ways to practise (cards, document quizzes, mock tests, the
mistake bank, practice problems, forgotten-card groups, mix-ups, Feynman), and
each reports on its own. Nothing shows a student the subject as a whole: which
ideas they hold, which they do not, and which weak idea rests on another weak
one. The map answers "what should I study next in this subject, and why",
with the reason visible.

## Decisions taken with the user

1. **One map per notebook.** A subject has 15–30 concepts, which fits on one
   screen; links inside one subject are more trustworthy than across subjects.
2. **Free network, one card per concept.** Each concept is its own card (name,
   a mastery bar, one line of real numbers such as "nhớ 2/6 thẻ · sai 3/5
   câu"), joined by "needs this first" arrows. Chosen over a layered ladder
   and a plain list, in the visual companion (`map-layout-v2`, option 2).
3. **Lives in the notebook page**, as a "Tài liệu · Bản đồ" switch
   (`?view=map`). Progress links to it per notebook.
4. **Mastery = two signals, coloured by the weaker one.**
   - *Hiểu* (understanding): Bayesian Knowledge Tracing over the concept's
     quiz answers, mock-test answers and practice-problem submits.
   - *Nhớ* (memory): FSRS retrievability today of the concept's reviewed
     cards, the same arithmetic as the test-day forecast.
   The two signals lead to different actions (review cards vs. practise
   problems), which a single blended number could not. The weaker-signal
   rule is a design decision, not learned from data; the report says so.
5. **The map must look good.** Paper-style cards with the existing two-layer
   shadow, soft curved arrows, smooth selection transitions, checked by
   screenshot on desktop and phone.

## Concepts, links and attachment

- **Concepts** are the documents' key points (`Source.key_points`). Key points
  from different documents that say the same thing are merged (TF-IDF
  similarity of point + passage, threshold fixed in notebook 10). A document
  without key points contributes none; the map says so and offers "Rút ý
  chính" (one request, as today).
- **Links**: one request per notebook. The model gets the concepts and
  returns pairs "A is needed before B", each with a one-sentence reason. Kept
  only if both ends exist; at most 3 prerequisites per concept; cycles
  broken by reading the pairs in reply order and dropping any pair that
  would close a loop (the model gives no confidence to rank them). Cached on the
  notebook with a hash of its concept ids; recomputed only when the concepts
  change.
- **Attachment** of practice to concepts, no model call:

  | Item | Compared with the concept's passage |
  |---|---|
  | Quiz and mock-test question | the question's `source_excerpt` |
  | Flashcard | question + answer, among concepts of the card's sources |
  | Practice problem | its checkpoints' `basis` quotes |

  The best match above the threshold wins; below it the item is "unattached"
  rather than forced onto a wrong concept.

## Mastery and the next action

- **Hiểu (BKT).** Events in time order; a correct answer or a passed submit
  counts as correct. Four parameters (initial, learn, guess, slip) fitted on
  ASSISTments 2009 in notebook 10, with a separate guess for multiple choice
  (`choose_1`) and for written answers (`algebra`, `fill_in_1`, used for
  practice problems).
- **Nhớ (FSRS).** Mean retrievability today of the concept's reviewed cards,
  shown as "nhớ k/n thẻ" over the n reviewed cards, with the cards never
  reviewed counted apart ("· 4 thẻ chưa học").
- **State**, from the weaker available signal: strong (≥ 0.8), shaky
  (0.5–0.8), weak (< 0.5), not studied (no events). The thresholds are
  checked in notebook 10. One event (one answer, submit or card review)
  only → "mới luyện 1 lần", faint border.
- **Action**, from the weaker signal:
  - memory weaker → "Ôn N thẻ" (relearn mode, `/dashboard/flashcards?cards=`);
  - understanding weaker → "Làm bài vận dụng" if the concept has one, else
    "Luyện 5 câu" (the existing weak-concept practice: one request writing 5
    questions from the concept's passages); a problem not yet mastered is
    offered before a mastered one.
  - a strong concept gets no button; its advice says scheduled reviews are
    enough.
  - a prerequisite that is weak or shaky is recommended first, with a button
    that selects its card.
- Computed without model calls, cached per user and notebook, invalidated by
  new activity.

## Interface

- `@xyflow/react` (React Flow, MIT) for pan, zoom (pinch on phones) and
  arrows; the cards are our own component.
- **Layout is ours and deterministic**: prerequisites to the left, dependants
  drift right, staggered so it reads as a network, not columns. Same data,
  same picture. Fit to screen on open; "Về giữa" and "Chỉ hiện chỗ yếu"
  (fades strong cards).
- **Selecting a card** highlights it and its incoming arrows. Desktop: detail
  panel on the right. Phone: bottom sheet. The panel shows the two signals,
  the advice, the action button, and the reason of each prerequisite arrow.
- **States**: no key points (guide + "Rút ý chính" per document); links being
  found (cards first, arrows when ready); links unavailable (cards and colours
  still shown, "Chưa tìm được mối liên hệ, thử lại sau").
- **Accessibility**: Tab/Enter move between cards; a visually hidden list
  carries the same content for screen readers.
- Existing palette and fonts; action buttons in their mode colour.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/notebooks/<id>/map/` | concepts, edges (or `edges_pending`), per-concept signals, state, action, unattached count |
| POST | `/api/notebooks/<id>/map/links/` | (re)find links; one request; throttled |

Access follows `notebooks_for(user)`; mastery is always the caller's own.

## Notebook 10 (`10_knowledge_map.ipynb`)

1. BKT on ASSISTments 2009 (4,148 students, 274k responses, 139 skills),
   split by student; AUC against a recent-accuracy baseline; per answer type
   guess; thresholds for the three states.
2. Attachment: about 60 cards and questions of the demo account labelled by
   hand with their key point; accuracy and the similarity threshold.
3. Links found on the demo notebooks: counted and listed for a reader to
   judge (no gold standard exists).

## Testing

Key-point merging; link filtering (cycles, unknown ids, the cap of 3); BKT
update; weaker-signal state and action choice; access to the map; map still
served when the link request fails. Frontend: the layout is deterministic and
cards do not overlap.

## Data

ASSISTments 2009–2010 skill builder (Feng, Heffernan & Koedinger 2009), via
the Hugging Face mirror `Atomi/ASSISTments2009` (per-student sequences).
Free for research with citation; kept out of git like the Duolingo traces,
with the download command in `datasets/README.md`.

## Out of scope

A map across notebooks; links edited by hand; teacher-made concept lists.
