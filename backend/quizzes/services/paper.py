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

#: Bounds on what a student can request for a sitting. A floor exists at all
#: because a one-question or one-minute "paper" measures nothing — it cannot
#: tell a student anything about their readiness, so it is not a smaller
#: version of the feature, it is a broken one. The ceiling exists because an
#: unbounded count turns one "start a test" press into an unbounded sample and
#: an unbounded number of frozen `MockTestQuestion` rows.
MIN_QUESTIONS = 5
MAX_QUESTIONS = 50
MIN_DURATION_MINUTES = 5
MAX_DURATION_MINUTES = 180


def clamp_int(value, minimum: int, maximum: int, default: int) -> int:
    """Parse `value` as a whole number and clamp it into [minimum, maximum].

    `None` (the field was omitted) yields `default` rather than an error —
    that is the normal case, not a bad request. Anything else that is not
    genuinely a whole number raises `ValueError`, so the caller can turn it
    into a 400 naming the offending field instead of silently coercing junk
    into a number. That includes `bool`: Python's `bool` is a subclass of
    `int`, so `isinstance(True, int)` is true, and without an explicit check
    `True` would quietly become `1`.

    Accepts a plain `int`, a whole-valued `float` (JSON has no distinct
    integer type, so a body decoded from JSON may hand back `20.0` for a
    field a form would have sent as `"20"`), or a string of digits. A
    fractional float or a non-digit string is rejected.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f'expected a whole number, got {value!r}')
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f'expected a whole number, got {value!r}')
        parsed = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        digits = stripped[1:] if stripped[:1] == '-' else stripped
        if not digits.isdigit():
            raise ValueError(f'expected a whole number, got {value!r}')
        parsed = int(stripped)
    else:
        raise ValueError(f'expected a whole number, got {value!r}')
    return max(minimum, min(maximum, parsed))


def _answer_matches(given: str | None, expected: str | None) -> bool:
    """Whether a submitted answer counts as correct against the stored one.

    Grading is deliberately lenient about case and surrounding whitespace and
    nothing else: the student is being tested on the material, not on their
    typing, so "paris" and "  Paris  " both count against a correct answer of
    "Paris". `casefold()` rather than `lower()` because it folds case more
    correctly across languages (e.g. German ß vs "ss"), which `lower()` alone
    would miss.
    """
    return (given or '').strip().casefold() == (expected or '').strip().casefold()


def typed_verdict(given: str | None, expected: str | None) -> str:
    """A typed missing word against the hidden one: "correct", "close" (a
    missing accent, or one slip in a long word) or "wrong"; "empty" when
    nothing was typed. The same check as lib/cloze.ts, which shows it."""
    said, meant = _plain(given), _plain(expected)
    if not said:
        return 'empty'
    if said == meant:
        return 'correct'
    if _unaccented(said) == _unaccented(meant):
        return 'close'
    if len(meant) >= 6 and _edits(said, meant) <= 1:
        return 'close'
    return 'wrong'


def typed_matches(given: str | None, expected: str | None) -> bool:
    """A typed answer counts when it is right or close: the student is
    tested on the idea, not on Telex."""
    return typed_verdict(given, expected) in ('correct', 'close')


def _plain(text: str | None) -> str:
    import re
    import unicodedata
    text = unicodedata.normalize('NFC', text or '').lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]|_', ' ', text)).strip()


def _unaccented(text: str) -> str:
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c)).replace('đ', 'd')


def _edits(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        row = [i]
        for j in range(1, len(b) + 1):
            row.append(min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1])))
        prev = row
    return prev[len(b)]


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
    # Left at full precision on purpose: this dict only feeds the weight
    # thresholds below, never a display. Rounding here would let a genuine
    # 84.95% round up to 85.0 and flip STRONG a comparison early (and the
    # mirror case at the WEAK boundary), which is a silent misclassification
    # for no benefit.
    return {sid: correct / total * 100
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

    # Drop duplicate ids, keeping the first occurrence. The next task builds
    # `pool` by matching questions to a notebook's documents, which can yield
    # more than one entry for the same question (e.g. one row per matching
    # source before aggregation). MockTestQuestion has a unique_together on
    # (mock_test, question), so an undetected duplicate here would surface as
    # an IntegrityError on save rather than as the duplicated question that
    # actually caused it.
    deduped = []
    seen_ids = set()
    for entry in pool:
        eid = entry.get("id")
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        deduped.append(entry)

    # Sorted by id before drawing so each entry's random key depends on the
    # entry's identity, not on its position in `pool`. rng.random() is called
    # once per position in iteration order, so without this sort, the same
    # seed over the same items in a different order (e.g. a queryset without
    # an explicit ORDER BY, which Postgres does not guarantee across calls)
    # would hand out keys to the wrong entries and silently produce a
    # different paper — defeating the reproducibility `seed` promises.
    deduped.sort(key=lambda entry: entry["id"])

    rng = random.Random(seed)
    scored = []
    for entry in deduped:
        weight = max(question_weight(entry, weights), 1e-9)
        scored.append((rng.random() ** (1.0 / weight), entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _key, entry in scored[:count]]
