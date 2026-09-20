"""Which questions a student still owes.

A question enters the bank the first time it is answered wrong and leaves
once it has been answered right twice in a row since — one right answer
after a miss is as likely luck as learning. Blank answers are neither.
Evidence comes from quizzes and mock tests alike; the view assembles it,
this module only applies the rule. Django-free.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional


def is_owed(history: list[Optional[bool]]) -> bool:
    """`history` is one question's answers oldest to newest; None is blank."""
    graded = [h for h in history if h is not None]
    if not any(h is False for h in graded):
        return False
    return graded[-2:] != [True, True]


def owed_question_ids(events: Iterable[tuple[int, object, Optional[bool]]]) -> set[int]:
    """From (question_id, answered_at, is_correct) events in any order."""
    by_question: dict[int, list[tuple[object, Optional[bool]]]] = defaultdict(list)
    for qid, when, correct in events:
        by_question[qid].append((when, correct))
    return {qid for qid, rows in by_question.items()
            if is_owed([c for _, c in sorted(rows, key=lambda r: r[0])])}
