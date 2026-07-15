"""Spaced repetition: when a card should come back, and what is owed today.

Two halves. `next_schedule` is the SM-2 step — given how a card was graded and
where its schedule stood, where does it stand next. `rank_due_cards` reads those
schedules back and answers the only question a learner actually asks: what
should I study now.

Kept free of Django imports so both can be unit-tested without a database — see
tests/test_spaced_repetition.py. The caller owns persistence; this deals only in
intervals and dates it is handed.
"""
from __future__ import annotations

from datetime import date
from typing import NamedTuple

# Grades, easiest-to-recall last. These mirror CardReview.RESULT_CHOICES.
AGAIN, HARD, GOOD, EASY = "again", "hard", "good", "easy"
RESULT_VALUES = (AGAIN, HARD, GOOD, EASY)

#: Grades that count as a successful recall when reporting accuracy. This module
#: is the source of truth; analytics.insights mirrors it (a test holds them
#: level) because it is loaded standalone and cannot import from here.
CORRECT_RESULTS = frozenset({GOOD, EASY})

# A card can never become harder than this, or a single bad day would push its
# interval growth to nothing and the card would resurface forever.
MIN_EASE_FACTOR = 1.3


class Schedule(NamedTuple):
    interval: int        # days until the card should be seen again
    ease_factor: float   # SM-2 multiplier; higher means the card grows faster
    repetitions: int     # consecutive successful recalls


#: Where a card starts before its first review (matches the CardReview defaults).
INITIAL = Schedule(interval=1, ease_factor=2.5, repetitions=0)


def next_schedule(result: str, *, interval: int, ease_factor: float,
                  repetitions: int) -> Schedule:
    """Advance a card's schedule by one review.

    Pass the card's *current* state; the returned state must be carried into the
    next review, otherwise every review restarts at repetitions=1 and intervals
    never lengthen.
    """
    if result not in RESULT_VALUES:
        raise ValueError(f"unknown grade {result!r}; expected one of {RESULT_VALUES}")

    repetitions += 1

    if result == AGAIN:
        # Forgotten: back to square one, and the card earns a harder rating.
        return Schedule(1, max(MIN_EASE_FACTOR, ease_factor - 0.2), 0)

    if result == HARD:
        # Recalled, but with effort: stretch the gap barely at all — yet stretch
        # it. Multiplying alone cannot, since int(1 * 1.2) is 1, which trapped a
        # short-interval card at a daily appearance that remembering could never
        # end. Only forgetting outright should hold a card at one day.
        return Schedule(max(interval + 1, int(interval * 1.2)),
                        max(MIN_EASE_FACTOR, ease_factor - 0.15),
                        repetitions)

    if result == GOOD:
        # The first two successes use fixed gaps; after that the card's own ease
        # takes over, which is what makes intervals grow exponentially.
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 3
        else:
            interval = int(interval * ease_factor)
        return Schedule(interval, ease_factor, repetitions)

    # EASY: same stretch as a good recall, plus a lasting ease bonus.
    return Schedule(int(interval * ease_factor), ease_factor + 0.1, repetitions)


# Why a card is in the study queue. A due card is being forgotten right now; a
# new card has simply never been seen.
STATUS_DUE = "due"
STATUS_NEW = "new"


def latest_schedule(reviews: list[dict]) -> dict[int, date]:
    """Each card's standing schedule, from its most recent review.

    Rows are ``{"flashcard_id", "next_review_date", "review_date"}``. A card
    accumulates one row per review; only the newest describes where it stands,
    the rest are history. Order of the rows does not matter.
    """
    newest: dict[int, dict] = {}
    for review in reviews:
        card_id = review["flashcard_id"]
        seen = newest.get(card_id)
        if seen is None or review["review_date"] > seen["review_date"]:
            newest[card_id] = review
    return {card_id: r["next_review_date"] for card_id, r in newest.items()}


def rank_due_cards(cards: list[dict], schedule: dict[int, date], today: date,
                   limit: int) -> list[dict]:
    """The cards worth studying now, most urgent first.

    A card is due once its scheduled date arrives, and new if it has never been
    reviewed. Cards scheduled ahead are left out entirely — declining to show
    what you still know is the whole point of spaced repetition, and is why this
    cannot be answered by ranking cards on how often they were failed.

    Overdue cards lead, longest-overdue first, because those are being forgotten
    while new cards are only an opportunity. Each result keeps whatever fields
    the caller passed in, so it serves both a study page and a summary list.
    """
    due, new = [], []
    for card in cards:
        next_date = schedule.get(card["id"])
        if next_date is None:
            new.append({**card, "status": STATUS_NEW, "overdue_days": 0})
        elif next_date <= today:
            due.append({**card, "status": STATUS_DUE,
                        "overdue_days": (today - next_date).days})

    # Sort by id first so equal urgency keeps a stable, predictable order.
    due.sort(key=lambda c: c["id"])
    due.sort(key=lambda c: c["overdue_days"], reverse=True)
    new.sort(key=lambda c: c["id"])
    return (due + new)[:limit]


def next_due_batch(schedule: dict[int, date], today: date) -> tuple[date | None, int]:
    """When cards next return, and how many return then.

    An empty queue is the algorithm succeeding, but saying only "nothing due"
    leaves that indistinguishable from a broken schedule — the reader has no way
    to tell working from failed. The return date is the evidence.
    """
    future = [d for d in schedule.values() if d and d > today]
    if not future:
        return None, 0
    soonest = min(future)
    return soonest, sum(1 for d in future if d == soonest)


def due_counts(cards: list[dict], schedule: dict[int, date], today: date) -> dict[str, int]:
    """How much study is owed right now: due, of which overdue, and new.

    Deliberately counts rather than names. Showing a card's question outside the
    study page hands the learner a free look at it minutes before they grade
    their own recall, which inflates the grade and so corrupts the very schedule
    this exists to report. `due + new` is exactly the size of the queue
    rank_due_cards would hand back.
    """
    counts = {"due": 0, "overdue": 0, "new": 0}
    for card in cards:
        next_date = schedule.get(card["id"])
        if next_date is None:
            counts["new"] += 1
        elif next_date <= today:
            counts["due"] += 1
            if next_date < today:
                counts["overdue"] += 1
    return counts
