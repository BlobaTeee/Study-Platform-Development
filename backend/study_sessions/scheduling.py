"""The SM-2 spaced-repetition step, as a pure function.

Given how a card was graded and where its schedule stood, this returns where the
schedule stands next. Kept free of Django imports so it can be unit-tested
without a database — see tests/test_spaced_repetition.py.

The caller owns persistence and the calendar: this deals only in intervals.
"""
from __future__ import annotations

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
        # Recalled, but with effort: stretch the gap barely at all.
        return Schedule(max(1, int(interval * 1.2)),
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
