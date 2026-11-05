# Build the map yourself (Tự dựng bản đồ): design

The user felt the knowledge map was not worth using: it shows mastery, and its
buttons repeat what other pages offer. On 2026-10-30 they chose to make it a
way of studying, where the student builds links between concepts and explains
each one. Constructing a concept map beats studying a finished one (Nesbit &
Adesope, 2006).

## Revision, 2026-11-04

The first version handed the student about six concepts the AI had chosen,
each with its description. The user's feedback:

- the cards were made by the AI, so nothing was built "yourself";
- the column of reason boxes on the right piled up, and it was hard to tell
  which box went with which line;
- with many links, the lines crossed into a tangle.

The user then chose:

| Question | Choice |
|---|---|
| Who makes the cards | The student writes every one, from memory |
| Where the reason is written | Next to the line it explains, not in a side column |
| Layout | Cards can be dragged anywhere; picking a card or a line fades the others |

## Revision, 2026-11-05: one document, in its own page

The user still found the two maps hard to use. The notebook map (30 concepts
for Biology) was too much to take in. The redraw step, which showed only a
document's title, did not say where its content came from. Now:

- The notebook-wide "Bản đồ" tab is gone.
- Each document's "Ý chính" section has a List / Map switch:
  - the list shows each key point's mastery state;
  - the map shows only that document's concepts (8 to 15) and the links
    between them. It is sized to fit the page width at a readable zoom.
- **Tự vẽ lại từ trí nhớ** sits in that same section. It hides the key points
  while the student draws, then compares against exactly those key points.
  There is no step for choosing a topic: the topic is the document being read.

The flow below is otherwise unchanged; step 1 now happens by opening a document.

## Flow

1. **Topic.** The student picks one document of the notebook that has key
   points; at least 3 are needed. Only its title is shown, with no hints.
2. **Recall.** They type the concepts they remember, one card each, from 3
   to 20 cards. A new card is placed in a free spot and can be dragged
   anywhere. This step is retrieval practice.
3. **Link.** Press a card, then another, to join them. Each line is
   numbered. Pressing a number, or a line just made, opens a small box next
   to it for the "why", and the box can also delete the link.
   - Picking a card or a link brightens its lines and fades the rest.
   - The work in progress is kept in the browser for that document, so
     leaving the page loses nothing.
4. **Compare.** One AI request receives the document's key points, the
   student's cards and their links. It returns:
   - for each card, the key point it matches, or none;
   - for each link, a verdict (correct / partial / wrong) and one sentence
     of feedback in the student's language.

   The result, shown under the canvas, has three parts:
   - "Recalled 5 of 9 key points", with the ones not mentioned listed;
   - each link coloured by its verdict, with its feedback, numbered like
     its line;
   - the document's own links between concepts the student recalled but did
     not join, drawn dashed (from the stored map, no request).

## Counting toward the map

A link whose card matches a key point is evidence for that point's concept:
*correct* counts right, *wrong* counts wrong, *partial* counts neither. Cards
that match no key point carry no evidence. The events enter the same BKT
trace as quiz answers.

## Server

- `GET map/build/`: the documents that can be a topic.
- `POST map/build/` with `{source, cards, links}`: grades the submission and
  stores the round. Nothing is stored if grading fails, so it can be sent
  again.
- Model `MapBuild` holds:
  - user, notebook, source;
  - cards: `{id, label, match_key, match_label}`;
  - links, with their verdicts and feedback;
  - missed links and missed points;
  - when it was graded.
- Limits:
  - 3 to 20 cards, each label 1 to 80 characters, no two labels the same;
  - 1 to 30 links, each between two different cards, each pair once;
  - a "why" of 3 to 400 characters.

## Not in this version

Relation types, and sharing a built map with the group.
