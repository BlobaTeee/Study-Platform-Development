"""Study insights derived from the user's own cards and performance.

Replaces the old fixed-taxonomy recommender, which could only suggest subjects
from a 5-subject STEM list and so returned irrelevant topics for real uploaded
documents. Everything here is computed from the user's actual review history.

No Django imports: views pass ORM data in as plain dicts, so this stays
unit-testable in isolation.
"""
from __future__ import annotations

# Study modes that produce evidence of knowing a document. Adding a mode later
# means adding a kind and an adapter that emits events — per_source_mastery
# itself stays untouched, because accuracy does not depend on the mode.
KIND_FLASHCARD = "flashcard"
KIND_QUIZ = "quiz"

# How a self-graded review maps onto "did you recall it?". Matches the split the
# study-session stats have always used: only good/easy count as a success.
CORRECT_RESULTS = frozenset({"good", "easy"})
# "again" was retired from the grade scale on 2026-07-25. Rows recorded before
# then still exist, and must keep counting as failures — dropping it here would
# quietly rewrite every affected learner's past accuracy.
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


def flashcard_events(cards: list[dict]) -> list[dict]:
    """Adapt flashcards (with review counts attached) to study events.

    `source_ids` is the card's resolved relation; a card with none — written
    by hand, or whose documents were deleted — is still an event, it just
    counts toward no document.
    """
    return [
        {
            "kind": KIND_FLASHCARD,
            "source_ids": list(card.get("source_ids", [])),
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
            "source_ids": list(question.get("source_ids", [])),
            "correct": tallies.get(question["id"], {}).get("correct", 0),
            "incorrect": tallies.get(question["id"], {}).get("incorrect", 0),
        }
        for question in questions
    ]


def _mastery(events: list[dict], groups_of, titles: dict[int, str], id_key: str) -> list[dict]:
    """Shared tally behind the per-source and per-notebook views.

    `groups_of(event)` names the groups an event counts toward — a set, so an
    item is credited to each group once no matter how many of its sources land
    there. Groups missing from `titles` are ignored (deleted, or never existed).
    """
    totals: dict[int, dict] = {}
    for event in events:
        for gid in groups_of(event):
            if gid not in titles:
                continue
            bucket = totals.setdefault(
                gid, {"correct": 0, "incorrect": 0, "cards": 0, "questions": 0}
            )
            bucket["correct"] += event.get("correct", 0)
            bucket["incorrect"] += event.get("incorrect", 0)
            bucket["cards" if event.get("kind") == KIND_FLASHCARD else "questions"] += 1

    out = []
    for gid, b in totals.items():
        reviews = b["correct"] + b["incorrect"]
        out.append({
            id_key: gid,
            "title": titles[gid],
            "cards": b["cards"],
            "questions": b["questions"],
            "reviews": reviews,
            "accuracy": round(b["correct"] / reviews * 100, 1) if reviews else None,
        })

    # Weakest first; never-studied groups go last (nothing to act on yet).
    out.sort(key=lambda r: (r["accuracy"] is None, r["accuracy"] if r["accuracy"] is not None else 0))
    return out


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
    return _mastery(events, lambda e: set(e.get("source_ids", [])), source_titles, "source_id")


def per_notebook_mastery(events: list[dict], source_to_notebook: dict[int, int],
                         notebook_titles: dict[int, str]) -> list[dict]:
    """How well the user knows each notebook, weakest first.

    Same evidence as `per_source_mastery`, rolled up a level. Not a sum of the
    per-source rows: a card generated from two sources in the same notebook
    would then count twice for it, so each event is credited to the *set* of
    notebooks its sources belong to. Sources with no notebook on record are
    ignored, and a notebook nobody has studied from is absent, not 0%.
    """
    def notebooks_of(event):
        return {source_to_notebook[sid] for sid in event.get("source_ids", [])
                if sid in source_to_notebook}
    return _mastery(events, notebooks_of, notebook_titles, "notebook_id")


def daily_activity(reviews: list[dict], mock_tests: list[dict], today, days: int) -> dict:
    """The last `days` days of study, one entry per day, oldest first.

    `reviews` are ``{"date": date, "result": str}`` — already in the student's
    own zone, which is the caller's job; a review at 00:30 belongs to the day
    the student was awake for, not the server's. `mock_tests` are
    ``{"date": date, "score": float}``.

    Every day of the window is present even with nothing in it: the Analytics
    strip shows a gap for a skipped day, and it can only do that if the day is
    there to be empty. Grades outside the known set (seed rows, retired
    grades) are not counted, same as everywhere else in this module.
    """
    from datetime import timedelta

    start = today - timedelta(days=days - 1)
    buckets = {
        start + timedelta(days=i): {"reviews": 0, "correct": 0, "mock_scores": []}
        for i in range(days)
    }
    for review in reviews:
        bucket = buckets.get(review["date"])
        result = review.get("result")
        if bucket is None or (result not in CORRECT_RESULTS and result not in INCORRECT_RESULTS):
            continue
        bucket["reviews"] += 1
        if result in CORRECT_RESULTS:
            bucket["correct"] += 1
    for test in mock_tests:
        bucket = buckets.get(test["date"])
        if bucket is not None:
            bucket["mock_scores"].append(test["score"])

    def accuracy(correct, reviews):
        return round(correct / reviews * 100, 1) if reviews else None

    out_days = [
        {"date": day, "reviews": b["reviews"], "correct": b["correct"],
         "accuracy": accuracy(b["correct"], b["reviews"]), "mock_scores": b["mock_scores"]}
        for day, b in buckets.items()
    ]
    total_reviews = sum(d["reviews"] for d in out_days)
    total_correct = sum(d["correct"] for d in out_days)
    return {
        "days": out_days,
        "summary": {
            "reviews": total_reviews,
            "accuracy": accuracy(total_correct, total_reviews),
            "mock_tests": sum(len(d["mock_scores"]) for d in out_days),
        },
    }
