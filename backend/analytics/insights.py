"""Study insights derived from the user's own cards and performance.

Replaces the old fixed-taxonomy recommender, which could only suggest subjects
from a 5-subject STEM list and so returned irrelevant topics for real uploaded
documents. Everything here is computed from the user's actual review history.

No Django imports: views pass ORM data in as plain dicts, so this stays
unit-testable in isolation.
"""
from __future__ import annotations

import re

SOURCE_TAG_PREFIX = "source:"

# Study modes that produce evidence of knowing a document. Adding a mode later
# means adding a kind and an adapter that emits events — per_source_mastery
# itself stays untouched, because accuracy does not depend on the mode.
KIND_FLASHCARD = "flashcard"
KIND_QUIZ = "quiz"

# How a self-graded review maps onto "did you recall it?". Matches the split the
# study-session stats have always used: only good/easy count as a success.
CORRECT_RESULTS = frozenset({"good", "easy"})
INCORRECT_RESULTS = frozenset({"again", "hard"})


def tally_reviews(reviews: list[dict]) -> dict[int, dict[str, int]]:
    """Fold CardReview rows into per-card correct/incorrect counts.

    Each row is ``{"flashcard_id": int, "result": str}``. Grades outside the
    four known ones are skipped rather than counted as failures.
    """
    tallies: dict[int, dict[str, int]] = {}
    for review in reviews:
        result = review.get("result")
        if result not in CORRECT_RESULTS and result not in INCORRECT_RESULTS:
            continue
        bucket = tallies.setdefault(review["flashcard_id"], {"correct": 0, "incorrect": 0})
        bucket["correct" if result in CORRECT_RESULTS else "incorrect"] += 1
    return tallies


def attach_review_counts(cards: list[dict], tallies: dict[int, dict[str, int]]) -> list[dict]:
    """Give each card the review counts the rest of this module reads.

    Cards with no reviews get zeros, which `card_priority` reads as unknown
    mastery rather than as failure.
    """
    return [
        {
            **card,
            "correct_count": tallies.get(card["id"], {}).get("correct", 0),
            "incorrect_count": tallies.get(card["id"], {}).get("incorrect", 0),
        }
        for card in cards
    ]


# The tag may be a field of its own (flashcards store a bare ``source:1,2``) or
# buried in prose (quizzes append ``[source:13]`` to their description), so this
# looks for it anywhere. Stopping at the first non-word character keeps the
# closing bracket out of the captured ids.
_SOURCE_TAG_RE = re.compile(re.escape(SOURCE_TAG_PREFIX) + r"([\w,]+)")


def parse_source_ids(text: str | None) -> list[int]:
    """Extract source ids from any text carrying a ``source:1,2`` tag.

    An item may be generated from several sources at once. Malformed pieces are
    skipped rather than failing the whole item.
    """
    if not text:
        return []
    ids = []
    for match in _SOURCE_TAG_RE.finditer(text):
        for piece in match.group(1).split(","):
            if piece.strip().isdigit():
                ids.append(int(piece.strip()))
    return ids


def flashcard_events(cards: list[dict]) -> list[dict]:
    """Adapt flashcards (with review counts attached) to study events."""
    return [
        {
            "kind": KIND_FLASHCARD,
            "source_ids": parse_source_ids(card.get("tags")),
            "correct": card.get("correct_count", 0),
            "incorrect": card.get("incorrect_count", 0),
        }
        for card in cards
    ]


def quiz_events(questions: list[dict], answers: list[dict]) -> list[dict]:
    """Adapt quiz questions and the user's answers to study events.

    Quiz answers are graded by the app rather than self-reported, so they are
    the firmer of the two kinds of evidence. Every question is an event, even
    an unanswered one — like an unreviewed card, it is still something to study.
    """
    tallies: dict[int, dict[str, int]] = {}
    for answer in answers:
        bucket = tallies.setdefault(answer["question_id"], {"correct": 0, "incorrect": 0})
        bucket["correct" if answer.get("is_correct") else "incorrect"] += 1

    return [
        {
            "kind": KIND_QUIZ,
            "source_ids": parse_source_ids(question.get("quiz_description")),
            "correct": tallies.get(question["id"], {}).get("correct", 0),
            "incorrect": tallies.get(question["id"], {}).get("incorrect", 0),
        }
        for question in questions
    ]


def per_source_mastery(events: list[dict], source_titles: dict[int, str]) -> list[dict]:
    """How well the user knows each document, weakest first.

    An event is one studied item — a flashcard or a quiz question — carrying the
    sources it came from and how often it was answered right or wrong. The mode
    that produced it does not affect accuracy; it only decides which column the
    item is counted in, so the reader can see what the score rests on.

    `source_titles` maps source id -> title; events pointing at a source that no
    longer exists are ignored. A document with no answers reports accuracy None
    rather than 0%, which would wrongly imply the user got it wrong.
    """
    totals: dict[int, dict] = {}
    for event in events:
        for sid in event.get("source_ids", []):
            if sid not in source_titles:
                continue
            bucket = totals.setdefault(
                sid, {"correct": 0, "incorrect": 0, "cards": 0, "questions": 0}
            )
            bucket["correct"] += event.get("correct", 0)
            bucket["incorrect"] += event.get("incorrect", 0)
            bucket["cards" if event.get("kind") == KIND_FLASHCARD else "questions"] += 1

    out = []
    for sid, b in totals.items():
        reviews = b["correct"] + b["incorrect"]
        out.append({
            "source_id": sid,
            "title": source_titles[sid],
            "cards": b["cards"],
            "questions": b["questions"],
            "reviews": reviews,
            "accuracy": round(b["correct"] / reviews * 100, 1) if reviews else None,
        })

    # Weakest first; never-studied documents go last (nothing to act on yet).
    out.sort(key=lambda s: (s["accuracy"] is None, s["accuracy"] if s["accuracy"] is not None else 0))
    return out
