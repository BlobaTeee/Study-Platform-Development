"""How a sat paper is weighed and timed: each part's points, scaled so the
whole is worth 10, and the minutes it is given. Used by a paper the student
brings to the mock-test page (services/papers.py).

Until 2026-11-26 a practice set could also be sat here as a paper; the user
asked for practice and mock tests to stand apart, so that is gone.
"""
import math

#: What each kind is worth before the paper is scaled to 10. As the THPT
#: paper weighs them: a Part I question 0.25, a Part II question (four
#: statements) 1, a Part III answer 0.25; a written problem 1.
BASE_POINTS = {'choice': 0.25, 'true_false': 1.0, 'short': 0.25, 'written': 1.0}
#: Minutes each kind is given, to time the paper by what it holds.
MINUTES = {'choice': 1.5, 'true_false': 4, 'short': 3, 'written': 10}
TOTAL = 10.0


def weigh(rows: list[dict]) -> int:
    """Each row's points, the whole worth 10 (set on the rows), and the
    minutes the paper is given."""
    base = sum(BASE_POINTS[r['section']] for r in rows) or 1.0
    for r in rows:
        r['points'] = round(BASE_POINTS[r['section']] * TOTAL / base, 3)
    minutes = sum(MINUTES[r['section']] for r in rows)
    return int(min(180, max(10, 5 * math.ceil(minutes / 5))))

