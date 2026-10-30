# Build the map yourself (Tự nối bản đồ): design

The user felt the knowledge map was not worth using. It shows mastery, and
its buttons repeat what other pages already offer. On 2026-10-30 they chose
to make it a way of studying: the student builds the links between concepts
and explains each one, then compares the result with the document's map.
Constructing concept maps beats studying a finished one (Nesbit & Adesope,
2006). It is also unlike the cards and quizzes the app already has.

## Choices (the user's)

| Choice | Picked |
|---|---|
| Size of a round | About 6 concepts, around the weakest |
| What a link holds | One sentence explaining why the two are related; no relation type |
| Does it count | Yes: graded links are evidence of understanding on the map |

## Flow

1. In the notebook's map, the student presses **Tự nối bản đồ**.
2. The round picks about 6 concepts. It starts from the weakest (weak, then
   shaky, then not studied, then strong) and walks the document's links out
   from it, so the concepts belong together. If the notebook has 6 or fewer,
   all of them are used. If the document's links were never found, they are
   found first (one AI request, cached as before).
3. The concepts appear with no lines between them. The student links two by
   pressing one and then the other. This works by mouse, touch or keyboard;
   on a desktop, dragging between handles also works. Each link gets a
   one-sentence "why". A link can be removed.
4. **Nộp** sends all links in one AI request. Each link is judged
   *correct*, *partial* or *wrong*, with one sentence of feedback in the
   notebook's language. The document's links that the student did not make
   are listed as **missed**, with their stored reason (no AI).
5. The result is drawn on the same canvas: the student's links in green, amber
   or red, and the missed ones dashed. Next to it is the list of feedback.
   From there the student can **do another round** or go back to the map.

## Counting toward the map

Each graded link becomes an event for both of its concepts:
- *correct* = right;
- *wrong* = wrong;
- *partial* counts as neither.

The events have the `written` kind and enter the same BKT trace as quiz
answers and practice submits, so the map's colours move after a round.

## Server

- `ml_pipeline.concept_map.pick_round(concepts, edges, size=6)`: a pure
  function that chooses the round.
- Model `MapBuild`: user, notebook, the concept keys, the submitted links
  with their verdicts and feedback, the missed links, and when it was made
  and graded.
- `notebooks/services/map_building.py`:
  - `start_round`, `clean_links`, `grade`;
  - `concept_events(user, notebook)` for `build_map`.
- Endpoints on the notebook, both throttled like other generation:
  - `POST map/build/` starts a round;
  - `POST map/build/<id>/submit/` grades it.
- Limits:
  - at least 3 concepts;
  - 1 to 15 links;
  - a "why" of 3 to 400 characters;
  - no link from a concept to itself, no duplicate pair;
  - a round is graded once.

## Not in this version

Relation types, letting students add their own concepts, and sharing a built
map with the group.

## Testing

- Pure tests for `pick_round`:
  - starts at the weakest;
  - follows the links;
  - fills up when the links run out;
  - a small notebook uses everything.
- Django tests:
  - only members;
  - link validation;
  - one AI request per submit;
  - partial does not count;
  - missed links come from the stored map;
  - the map's understanding moves after a round;
  - graded once.
- Frontend unit tests for the link list helpers.
- A screenshot pass.
