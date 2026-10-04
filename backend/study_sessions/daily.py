"""Today's share of the study queue, read from the database.

The rules themselves are in `scheduling` (pure, unit-tested); this only gathers
what they need. One plan, used by both the study page and the dashboard, so
the two cannot disagree about how much of today is left.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import NamedTuple

from django.conf import settings
from django.utils import timezone

from . import scheduling
from .models import CardReview


class DayPlan(NamedTuple):
    budget: scheduling.DailyBudget
    #: notebook -> days until its test, for tests this week.
    exam_days: dict[int, int]
    #: notebook -> new cards of that test to show today.
    exam_new: dict[int, int]
    #: unseen cards across all test notebooks, today's or not.
    exam_unseen: int


def _activity_rows(user, today: date) -> list[dict]:
    """Today's reviews, plus whether each of those cards was seen before.

    Two small queries rather than the user's whole history. A day is the
    server's local day, the same `timezone.localdate()` the schedule uses.
    """
    today_rows = list(CardReview.objects
                      .filter(user=user, review_date__date=today)
                      .values('flashcard_id', 'is_seed'))
    if not today_rows:
        return []
    card_ids = {r['flashcard_id'] for r in today_rows}
    earlier_rows = (CardReview.objects
                    .filter(user=user, flashcard_id__in=card_ids,
                            review_date__date__lt=today)
                    .values('flashcard_id', 'is_seed'))
    # Only "before today or not" matters to the rules, so any earlier date does.
    before = today - timedelta(days=1)
    return ([{**r, 'day': today} for r in today_rows]
            + [{**r, 'day': before} for r in earlier_rows])


def exam_days_for(user, now) -> dict[int, int]:
    """Days until each of this user's tests this week, by notebook.

    Only tests still ahead count — one sat this morning is over, whatever its
    date says. Tests are per person, so a classmate's plan never reorders
    someone else's queue.
    """
    from quizzes.models import PlannedTest
    rows = (PlannedTest.objects.filter(user=user, scheduled_for__gte=now)
            .values('notebook_id', 'scheduled_for'))
    tests = [{'notebook_id': r['notebook_id'], 'day': timezone.localdate(r['scheduled_for'])}
             for r in rows]
    return scheduling.exam_days(tests, timezone.localdate(now))


def plan_for(user, cards: list[dict], schedule: dict, today: date, now) -> DayPlan:
    """Today's plan over `cards` (each with `id` and `notebook_id`)."""
    rows = _activity_rows(user, today)
    reviewed, introduced = scheduling.todays_activity(rows, today)
    owed = scheduling.due_counts(cards, schedule, today)['due']
    budget = scheduling.daily_budget(
        review_limit=getattr(settings, 'DAILY_REVIEW_LIMIT', 40),
        new_limit=getattr(settings, 'DAILY_NEW_LIMIT', 10),
        reviewed_today=reviewed,
        introduced_today=introduced,
        due_now=owed,
    )

    exams = exam_days_for(user, now)
    notebook_of = {c['id']: c.get('notebook_id') for c in cards}
    unseen = Counter(notebook_of[c['id']] for c in cards
                     if schedule.get(c['id']) is None and notebook_of[c['id']] in exams)
    learned = Counter(notebook_of.get(card_id)
                      for card_id in scheduling.introduced_today_ids(rows, today)
                      if notebook_of.get(card_id) in exams)
    exam_new = scheduling.exam_new_allowance(dict(unseen), dict(learned), exams)
    return DayPlan(budget, exams, exam_new, sum(unseen.values()))
