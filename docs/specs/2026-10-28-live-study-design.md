# Live study (Học trực tiếp) — design

Main feature C from 2026-10-08: studying together, at the same time, in a
shared notebook. The user asked for it on 2026-10-28 and left the choices to
me while away; each choice below says why, so it can be undone cheaply.

## What it is

A round of questions everyone in a shared notebook answers at the same time,
one question at a time, with the answer shown to the whole group after each
question so they can talk it through. Questions come from the notebook's
existing quizzes (multiple choice and true/false). No AI request, so it works
when the Gemini quota is gone.

Why this shape and not a race: retrieval practice is what the app already
does alone. What a group adds is *peer instruction* (Mazur): commit to an
answer first, then see how the group split and argue it out. So the round
waits on the reveal screen until someone moves on, and the reveal shows how
many picked each option, not only who was fastest.

## Flow

1. **Open a room.** In a notebook with at least one usable question, anyone
   presses "Học trực tiếp" and picks the number of questions (5, 10 or 15) and
   the time per question (15, 30 or 60 s). The opener is the host. A notebook
   has at most one open room; pressing again joins it.
   Everyone else in the notebook gets a banner, wherever they are in the
   dashboard: "<name> mở phòng học trực tiếp · <notebook> — Vào phòng".
2. **Lobby.** Who has joined. Only the host can start.
3. **Question.** The question and its options, a countdown, and how many have
   answered. One answer each, no changing it. A late answer is refused.
4. **Reveal**, when everyone has answered or the time is up: the right option,
   how many picked each option, who got it right, the explanation, and the
   passage it came from. Waits for the host to go on; if the host has not
   pressed "next" 20 seconds after the reveal, anyone can, so a host who
   walked off does not strand the room.
5. **End.** Scores (one point per right answer; ties go to less total time),
   and for each player the questions they missed.

## Choices made

| Choice | Picked | Why |
|---|---|---|
| Where | A shared notebook, page `/dashboard/live/<id>` | The questions and the people are already there (NotebookMember). |
| Questions | Multiple choice and true/false from the notebook's published quizzes | Typed answers need the AI grader, which needs quota. |
| Which questions | The group's misses first: questions any member still owes (mistake bank), then random | The point of studying together is to fix what the group gets wrong. |
| Scoring | 1 per right answer, tie broken by time | A speed bonus rewards guessing, which is the opposite of the lesson. |
| Who moves on | The host; anyone after 20 s on a reveal | Time to discuss, without a stuck room. |
| Mistakes | Live answers count as evidence in the mistake bank | A miss in a group round is as real as one in a quiz. |
| Who can join | Members of the notebook only | Same rule as everything else in a shared notebook. |

## Server

App `live`, three tables:

- `LiveSession`: notebook, host, status (`lobby`, `question`, `reveal`,
  `finished`), the question ids chosen at the start, the current index,
  seconds per question, when the current question started and when it was
  revealed.
- `LiveParticipant`: session, user, joined at.
- `LiveAnswer`: session, user, question, index, the choice, right or not,
  milliseconds taken. Unique per (session, user, index).

Rules live in `live/services/rounds.py`. Views are thin REST calls: create or
join, start, answer, reveal, next, leave, get state. The clock is the
server's: an answer counts if it arrives within the time plus 2 s for the
network. Nothing runs in the background. When the time is up, any client asks
for the reveal and the server checks the deadline. A reveal or next that has
already happened is a no-op, so two clients pressing at once is fine.

Realtime uses the existing Socket.IO server. A client sends `live:join` with
the session id, the server checks membership and puts it in room
`live-<id>`. Every change is broadcast there as `live:state`. The REST GET
returns the same payload plus the viewer's own answer, so a client that
reconnects only has to fetch. The right answer is not in the payload before
the reveal. Opening a room emits `live:open` to the personal room
(`user-<id>`) of each notebook member.

## Not in this version

Leaderboards across rounds, weekly challenges, peer-graded summaries, voice
or video, rooms outside a notebook, typed answers. Each can come later on top
of the same tables.

## Testing

- Django tests for the rules:
  - only members can open or join;
  - one open room per notebook;
  - questions the group owes come first;
  - only the host starts;
  - one answer per question;
  - late answers are refused;
  - the reveal comes early once everyone has answered, and not before the
    deadline otherwise;
  - next is for the host, or anyone 20 s after the reveal;
  - the correct answer is hidden before the reveal;
  - the scores and tie-break;
  - live misses enter the mistake bank.
- Frontend unit tests for the countdown, the option split and the ranking.
- A screenshot pass through the read-only bridge.
