"""Choosing which questions make up a mock test.

A paper is drawn from every question a notebook's documents produced, weighted
so material the student answers badly turns up more often. Weighting rather than
selecting keeps a paper varied: a weak topic is likelier, never guaranteed, so
two sittings are not the same test.

No Django imports — the caller passes plain dicts, so the arithmetic and the
sampling stay unit-testable without a database.
"""
from __future__ import annotations

import random

#: Accuracy (percent) below which a document counts as weak, and above which it
#: counts as known. Mirrors the thresholds the recommendation engine already
#: uses, so the app does not disagree with itself about what "weak" means.
WEAK_ACCURACY = 60.0
STRONG_ACCURACY = 85.0

WEAK_WEIGHT = 1.5
NEUTRAL_WEIGHT = 1.0
STRONG_WEIGHT = 0.6


def source_accuracy(answer_rows: list[dict]) -> dict[int, float]:
    """Percent correct per source, from graded quiz answers.

    A source the student has never answered is absent rather than 0.0: zero
    would read as "got it wrong", which would push untouched material to the
    front of every paper.
    """
    totals: dict[int, list[int]] = {}
    for row in answer_rows:
        for sid in row.get("source_ids") or []:
            bucket = totals.setdefault(sid, [0, 0])
            bucket[0] += 1 if row.get("is_correct") else 0
            bucket[1] += 1
    return {sid: round(correct / total * 100, 1)
            for sid, (correct, total) in totals.items() if total}


def source_weights(accuracy: dict[int, float]) -> dict[int, float]:
    """Sampling weight per source: weak material weighs more."""
    weights = {}
    for sid, pct in accuracy.items():
        if pct < WEAK_ACCURACY:
            weights[sid] = WEAK_WEIGHT
        elif pct >= STRONG_ACCURACY:
            weights[sid] = STRONG_WEIGHT
        else:
            weights[sid] = NEUTRAL_WEIGHT
    return weights


def question_weight(entry: dict, weights: dict[int, float]) -> float:
    """A question weighs as much as the weakest source it came from.

    Taking the maximum means a question spanning a known and an unknown document
    is treated as worth asking, which is the cautious way round.
    """
    sids = entry.get("source_ids") or []
    if not sids:
        return NEUTRAL_WEIGHT
    return max(weights.get(sid, NEUTRAL_WEIGHT) for sid in sids)


def sample_paper(pool: list[dict], weights: dict[int, float], count: int,
                 seed=None) -> list[dict]:
    """`count` questions drawn from `pool` without replacement, weighted.

    Uses the Efraimidis–Spirakis key: each entry gets ``u ** (1 / w)`` for a
    uniform ``u``, and the largest keys win. Heavier entries push their keys
    toward 1, so they are likelier without ever being certain — and drawing by
    key rather than by repeated choice guarantees no question is asked twice.

    `seed` makes a paper reproducible, which is what lets the weighting be
    tested at all.
    """
    if count <= 0 or not pool:
        return []

    rng = random.Random(seed)
    scored = []
    for entry in pool:
        weight = max(question_weight(entry, weights), 1e-9)
        scored.append((rng.random() ** (1.0 / weight), entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _key, entry in scored[:count]]
