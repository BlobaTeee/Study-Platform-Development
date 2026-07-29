"""Deciding which planned tests are owed a reminder.

Pulled out of the management command so the rule can be tested without a
database, a mail backend, or a real clock — the three things that make
scheduled sending awkward to verify otherwise.
"""
from __future__ import annotations

from datetime import timedelta


def due_reminders(plans: list[dict], now) -> list[dict]:
    """The plans whose reminder should go out at `now`.

    A plan qualifies once its lead time has opened, provided nothing has been
    sent yet and the test has neither been sat nor already passed. Reminding
    someone about a test that has come and gone is noise, so those are dropped
    rather than sent late.

    Callers stamp `reminder_sent_at` after sending, which is what makes running
    this on a short schedule safe: an already-reminded plan can never qualify a
    second time.
    """
    due = []
    for plan in plans:
        if plan.get("reminder_sent_at") is not None or plan.get("taken"):
            continue
        scheduled = plan["scheduled_for"]
        if scheduled <= now:
            continue
        lead = timedelta(hours=plan.get("reminder_lead_hours") or 0)
        if scheduled - lead <= now:
            due.append(plan)
    return due
