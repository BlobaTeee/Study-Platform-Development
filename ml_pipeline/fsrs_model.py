"""Memory state from a card's review history: FSRS-6.

The Free Spaced Repetition Scheduler (open-spaced-repetition, MIT licence;
the model Anki uses) describes a card by its stability S, the days until
recall falls to 90%, and difficulty D, from 1 to 10. Recall after t days is
R = (1 + F t / S)^-decay. The parameters are FSRS-6's published defaults,
fitted on Anki review logs: flashcards graded by the learner, which is what
this app records. That is why they are used rather than the half-life
regression fitted on Duolingo's word drills in notebook 08, which overrated
recall for flashcards.

Formulas and parameters follow py-fsrs (fsrs/scheduler.py). A card's state
is rebuilt by replaying its reviews: the first grade sets S and D; a later
one on the same day uses the short-term formula; a later one on another day
uses the recall or forget formula at the recall the card had by then. The
app's three grades map to FSRS ratings Hard/"forgot" -> Again, Good -> Good,
Easy -> Easy.

No Django imports.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

PARAMETERS = (
    0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666,
    0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658,
    0.1542,
)
STABILITY_MIN = 0.001
MIN_DIFFICULTY, MAX_DIFFICULTY = 1.0, 10.0
AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4
#: The app's grades. "hard" is the button labelled "forgot it".
RATING = {'hard': AGAIN, 'good': GOOD, 'easy': EASY}

_w = PARAMETERS
DECAY = -_w[20]
FACTOR = 0.9 ** (1 / DECAY) - 1


@dataclass(frozen=True)
class MemoryState:
    stability: float
    difficulty: float
    last_review: datetime


def retrievability(elapsed_days: float, stability: float) -> float:
    """The chance of recall `elapsed_days` after the last review."""
    return (1 + FACTOR * max(elapsed_days, 0.0) / stability) ** DECAY


def _clamp_s(s: float) -> float:
    return max(s, STABILITY_MIN)


def _clamp_d(d: float) -> float:
    return min(max(d, MIN_DIFFICULTY), MAX_DIFFICULTY)


def _initial_difficulty(rating: int) -> float:
    return _w[4] - math.e ** (_w[5] * (rating - 1)) + 1


def first_review(rating: int) -> tuple[float, float]:
    return _clamp_s(_w[rating - 1]), _clamp_d(_initial_difficulty(rating))


def next_difficulty(difficulty: float, rating: int) -> float:
    delta = -(_w[6] * (rating - 3))
    damped = difficulty + (10.0 - difficulty) * delta / 9.0
    return _clamp_d(_w[7] * _initial_difficulty(EASY) + (1 - _w[7]) * damped)


def next_stability(stability: float, difficulty: float, elapsed_days: float, rating: int) -> float:
    if elapsed_days < 1:
        increase = math.e ** (_w[17] * (rating - 3 + _w[18])) * stability ** -_w[19]
        if rating != AGAIN:
            increase = max(increase, 1.0)
        return _clamp_s(stability * increase)
    r = retrievability(elapsed_days, stability)
    if rating == AGAIN:
        long_term = (_w[11] * difficulty ** -_w[12] * ((stability + 1) ** _w[13] - 1)
                     * math.e ** ((1 - r) * _w[14]))
        short_term = stability / math.e ** (_w[17] * _w[18])
        return _clamp_s(min(long_term, short_term))
    hard_penalty = _w[15] if rating == HARD else 1
    easy_bonus = _w[16] if rating == EASY else 1
    return _clamp_s(stability * (1 + math.e ** _w[8] * (11 - difficulty) * stability ** -_w[9]
                                 * (math.e ** ((1 - r) * _w[10]) - 1) * hard_penalty * easy_bonus))


def review(state: MemoryState | None, rating: int, when: datetime) -> MemoryState:
    """The state after one more review."""
    if state is None:
        s, d = first_review(rating)
        return MemoryState(s, d, when)
    elapsed = (when - state.last_review).total_seconds() / 86400
    s = next_stability(state.stability, state.difficulty, elapsed, rating)
    return MemoryState(s, next_difficulty(state.difficulty, rating), when)


def replay(reviews: Iterable[tuple[datetime, int]]) -> MemoryState | None:
    """Rebuild a card's state from its (when, rating) reviews."""
    state = None
    for when, rating in sorted(reviews, key=lambda r: r[0]):
        state = review(state, rating, when)
    return state
