"""Deciding how much to generate when a notebook cannot fill a paper.

A paper is sampled from the questions a notebook's documents have already
produced. When the student asks for more questions than exist, the shortfall
is generated on the spot rather than handing over a short paper.

That has a cost the rest of the feature does not: generation is model calls,
and a test start blocks on them. So the policy here is deliberately
conservative — ask only for what is missing, never more than one generation
yields, and stop early rather than chase a target that is not being reached.
The wall-clock budget is enforced by the caller, which owns the clock.

No Django imports, so the arithmetic is unit-testable on its own.
"""
from __future__ import annotations

#: The most questions one `generate_quiz_for_sources` call returns. It clamps
#: its own argument to this, so asking for more silently gets this many and a
#: caller that did not know would loop forever waiting for the rest.
QUIZ_MAX_PER_GENERATION = 15

#: A top-up round may ask for more than a quiz press does: it is one request
#: either way, and a 50-question paper on an empty notebook then fills in two
#: rounds instead of four.
TOPUP_PER_ROUND = 25

#: The generator also has a floor: ask for fewer than this and you still get
#: this many. Harmless — the extras join the pool for later tests — but it is
#: why a "top up by 1" round is not free.
QUIZ_MIN_PER_GENERATION = 4

#: A paper may ask for 50 questions against an empty notebook, which is four
#: generations and a dozen model calls. Rounds are capped so a student waits a
#: bounded time and then sits a slightly short paper, rather than waiting an
#: unbounded one for a perfect paper.
MAX_TOPUP_ROUNDS = 3

#: And capped again by wall clock, because rounds are not equal: a provider
#: timing out makes three rounds far slower than three fast ones.
#:
#: This bounds *additional* rounds, not the first one. A round is only checked
#: before it starts, so the true worst case for a single round is the
#: provider's own ceiling — RAG_CHUNKS x OLLAMA_TIMEOUT, which defaults to
#: 3 x 120s. Nothing here can shorten that; what it prevents is a slow first
#: round compounding into three. Lower OLLAMA_TIMEOUT to bound the first.
TOPUP_TIME_BUDGET_SECONDS = 90


def questions_to_request(pool_size: int, requested: int,
                         per_round_max: int = QUIZ_MAX_PER_GENERATION) -> int:
    """How many questions to ask the generator for in this round.

    Zero means the pool already covers the paper and nothing should be
    generated — the caller must treat that as "stop", not as "ask for none",
    since the generator's own floor would turn a zero request into four.
    """
    missing = requested - pool_size
    if missing <= 0:
        return 0
    return min(missing, per_round_max)


def should_continue(pool_size: int, previous_pool_size: int, requested: int,
                    rounds_done: int, seconds_spent: float,
                    max_rounds: int = MAX_TOPUP_ROUNDS,
                    budget_seconds: float = TOPUP_TIME_BUDGET_SECONDS) -> bool:
    """Whether another generation round is worth starting.

    Stops on any of: the paper is coverable, the round cap is reached, the
    time budget is spent, or the last round added nothing.

    That last condition is the important one. A document that has already
    given up every question it can produce will keep returning duplicates the
    pool rejects, so without it a thin notebook would burn the entire budget
    on rounds that cannot change the outcome.
    """
    if pool_size >= requested:
        return False
    if rounds_done >= max_rounds:
        return False
    if seconds_spent >= budget_seconds:
        return False
    if rounds_done > 0 and pool_size <= previous_pool_size:
        return False
    return True
