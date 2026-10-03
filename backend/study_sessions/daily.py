"""Today's share of the study queue, read from the database.

The rule itself is in `scheduling` (pure, unit-tested); this only gathers what
it needs. One definition, so the study page and the dashboard cannot disagree
about how much of today is left.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

from . import scheduling
from .models import CardReview


def todays_activity(user, today: date) -> tuple[int, int]:
    """(cards reviewed today, cards first studied today) for this user.

    Two small queries rather than the user's whole history: today's rows, and
    for just those cards, whether anything came before. A day is the server's
    local day, the same `timezone.localdate()` the schedule is built on.
    """
    today_rows = list(CardReview.objects
                      .filter(user=user, review_date__date=today)
                      .values('flashcard_id', 'is_seed'))
    if not today_rows:
        return 0, 0
    card_ids = {r['flashcard_id'] for r in today_rows}
    earlier_rows = (CardReview.objects
                    .filter(user=user, flashcard_id__in=card_ids,
                            review_date__date__lt=today)
                    .values('flashcard_id', 'is_seed'))
    # Only "before today or not" matters to the rule, so any earlier date does.
    before = today - timedelta(days=1)
    rows = ([{**r, 'day': today} for r in today_rows]
            + [{**r, 'day': before} for r in earlier_rows])
    return scheduling.todays_activity(rows, today)


def budget_for(user, due_now: int, today: date) -> scheduling.DailyBudget:
    reviewed, introduced = todays_activity(user, today)
    return scheduling.daily_budget(
        review_limit=getattr(settings, 'DAILY_REVIEW_LIMIT', 40),
        new_limit=getattr(settings, 'DAILY_NEW_LIMIT', 10),
        reviewed_today=reviewed,
        introduced_today=introduced,
        due_now=due_now,
    )


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
