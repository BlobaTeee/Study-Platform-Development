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
HARD, GOOD, EASY = "hard", "good", "easy"
RESULT_VALUES = (HARD, GOOD, EASY)

#: Grades that count as a successful recall when reporting accuracy. This module
#: is the source of truth; analytics.insights mirrors it (a test holds them
#: level) because it is loaded standalone and cannot import from here.
CORRECT_RESULTS = frozenset({GOOD, EASY})

#: Grades no longer offered, but still present on rows recorded before they were
#: retired. `next_schedule` rejects them; analytics must still classify them, or
#: a learner's history would silently lose its failures.
RETIRED_RESULTS = frozenset({"again"})

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

    if result == HARD:
        # Forgotten, or recalled only with effort: back to square one, and the
        # card earns a harder rating. This is now the only grade that resets a
        # card, so it is what stops material the learner cannot recall from
        # drifting steadily further away.
        return Schedule(1, max(MIN_EASE_FACTOR, ease_factor - 0.2), 0)

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


class DailyBudget(NamedTuple):
    """How much of the queue today still has room for."""
    reviews_left: int
    new_left: int


def daily_budget(*, review_limit: int, new_limit: int, reviewed_today: int,
                 introduced_today: int, due_now: int) -> DailyBudget:
    """Today's remaining share of reviews and of new cards.

    Two weeks away leaves hundreds of cards owed, and shown as one number that
    is the moment a learner gives up. So a day has a share; what does not fit
    stays due and leads tomorrow.

    New cards wait while more is owed than today can clear. Every card learned
    today is a review owed tomorrow, so introducing them during a backlog only
    deepens it — the "debt spiral" this exists to stop.
    """
    reviews_left = max(0, review_limit - reviewed_today)
    if due_now > reviews_left:
        new_left = 0
    else:
        new_left = max(0, new_limit - introduced_today)
    return DailyBudget(reviews_left=reviews_left, new_left=new_left)


def todays_share(counts: dict[str, int], budget: DailyBudget) -> dict:
    """What a summary says about today: its share, and honestly, what waits.

    `later` counts only due cards pushed to coming days. New cards held back
    are not debt — they were never owed — so they are not added to it;
    `new_paused` says why they are missing when the reason is the backlog
    rather than a spent daily allowance.
    """
    due_today = min(counts["due"], budget.reviews_left)
    return {
        "today": due_today + min(counts["new"], budget.new_left),
        "later": counts["due"] - due_today,
        "new_paused": counts["new"] > 0 and counts["due"] > budget.reviews_left,
    }


def todays_activity(rows: list[dict], today: date) -> tuple[int, int]:
    """(cards reviewed today, cards first studied today).

    Rows are ``{"flashcard_id", "day", "is_seed"}`` where `day` is the review's
    local date. A card counts once however often it was answered. Seed rows
    are no recall, so they never count as work done — but a card that has one
    inherited a place in the schedule, so answering it is a review, not a new
    card.
    """
    seen_before: set[int] = set()
    answered_today: set[int] = set()
    for row in rows:
        card = row["flashcard_id"]
        if row["day"] < today or row["is_seed"]:
            seen_before.add(card)
        elif row["day"] == today:
            answered_today.add(card)
    reviewed = answered_today & seen_before
    return len(reviewed), len(answered_today - seen_before)


#: A test closer than this puts its notebook first in the queue. A week is the
#: revision window most students actually work to.
EXAM_WINDOW_DAYS = 7


def exam_days(tests: list[dict], today: date,
              window: int = EXAM_WINDOW_DAYS) -> dict[int, int]:
    """Days until each notebook's next test, for tests inside the window.

    Rows are ``{"notebook_id", "day"}`` with `day` the test's local date. A
    test already sat gives no priority, and a notebook with several tests
    counts from the soonest.
    """
    out: dict[int, int] = {}
    for test in tests:
        days = (test["day"] - today).days
        if 0 <= days <= window:
            nb = test["notebook_id"]
            out[nb] = min(days, out.get(nb, days))
    return out


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
                   limit: int, budget: "DailyBudget | None" = None,
                   exam_days: dict[int, int] | None = None) -> list[dict]:
    """The cards worth studying now, most urgent first.

    A card is due once its scheduled date arrives, and new if it has never been
    reviewed. Cards scheduled ahead are left out entirely — declining to show
    what you still know is the whole point of spaced repetition, and is why this
    cannot be answered by ranking cards on how often they were failed.

    Overdue cards lead, longest-overdue first, because those are being forgotten
    while new cards are only an opportunity. Each result keeps whatever fields
    the caller passed in, so it serves both a study page and a summary list.

    With a `budget`, only today's share is handed back: at most
    `reviews_left` due cards and `new_left` new ones. The rest stay due and
    lead tomorrow's queue, since they will be the most overdue then.

    `exam_days` maps a notebook to the days until its test (see `exam_days`).
    A card for a test this week goes before older debt elsewhere, the sooner
    test first: when a day cannot clear everything, it clears what matters
    soonest. Cards carry `exam_in_days` so the page can say why.
    """
    exams = exam_days or {}
    due, new = [], []
    for card in cards:
        next_date = schedule.get(card["id"])
        exam = exams.get(card.get("notebook_id"))
        if next_date is None:
            new.append({**card, "status": STATUS_NEW, "overdue_days": 0,
                        "exam_in_days": exam})
        elif next_date <= today:
            due.append({**card, "status": STATUS_DUE,
                        "overdue_days": (today - next_date).days,
                        "exam_in_days": exam})

    def exam_first(card):
        # No test sorts after every test; sooner tests before later ones.
        days = card["exam_in_days"]
        return (days is None, days if days is not None else 0)

    # Ties fall back to id, so equal urgency keeps a stable, predictable order.
    due.sort(key=lambda c: (*exam_first(c), -c["overdue_days"], c["id"]))
    new.sort(key=lambda c: (*exam_first(c), c["id"]))
    if budget is not None:
        due = due[:budget.reviews_left]
        new = new[:budget.new_left]
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


class Streak(NamedTuple):
    current: int
    best: int
    last_date: date


def advance_streak(current: int, best: int, last_date: date | None, today: date) -> Streak:
    """Advance a study streak by one day of activity.

    A streak counts consecutive local days with at least one review. The record
    (`best`) survives a broken streak. Same-day repeats leave everything alone,
    so this is safe to call on every review rather than only the first.
    """
    if last_date is None:
        return Streak(1, max(best, 1), today)
    delta = (today - last_date).days
    if delta == 0:
        return Streak(current, best, last_date)
    if delta == 1:
        current += 1
        return Streak(current, max(best, current), today)
    # A gap (or a clock that moved backwards) restarts the count; the best holds.
    return Streak(1, max(best, 1), today)
