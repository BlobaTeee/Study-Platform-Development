"""Deciding which planned tests are owed a reminder.

Pulled out of the management command so the rule can be tested without a
database, a mail backend, or a real clock — the three things that make
scheduled sending awkward to verify otherwise.
"""
from __future__ import annotations

from datetime import timedelta


def _resolved(plan: dict) -> bool:
    """Whether this plan needs no further reminder decision at all.

    Sent, sat, or already marked skipped (a terminal state stamped once a
    plan's window has passed unsent, or its user has no email address — see
    the command) all mean the same thing here: nothing more to do.
    """
    return (plan.get("reminder_sent_at") is not None
            or plan.get("reminder_skipped_at") is not None
            or bool(plan.get("taken")))


def due_reminders(plans: list[dict], now) -> list[dict]:
    """The plans whose reminder should go out at `now`.

    A plan qualifies once its lead time has opened, provided nothing has been
    sent or skipped yet and the test has neither been sat nor already passed.
    Reminding someone about a test that has come and gone is noise, so those
    are dropped rather than sent late.

    Callers stamp `reminder_sent_at` after sending, which is what makes running
    this on a short schedule safe: an already-reminded plan can never qualify a
    second time. A plan already stamped `reminder_skipped_at` is excluded the
    same way, so a plan the command has given up on cannot resurface here either.
    """
    due = []
    for plan in plans:
        if _resolved(plan):
            continue
        scheduled = plan["scheduled_for"]
        if scheduled <= now:
            continue
        lead = timedelta(hours=plan.get("reminder_lead_hours") or 0)
        if scheduled - lead <= now:
            due.append(plan)
    return due


def missed_reminders(plans: list[dict], now) -> list[dict]:
    """Plans whose reminder window closed without ever being sent.

    This is the flip side of `due_reminders`' late-drop: if cron doesn't run
    for the whole lead window (down host, deploy gap, whatever), the plan
    never appears in `due_reminders` again once `scheduled_for` has passed —
    it just quietly stops being reminder-eligible, and nothing records that
    the student was owed a reminder that never went out. Callers should stamp
    `reminder_skipped_at` on whatever this returns (see the command) rather
    than send anything for it: a reminder for a test that has already
    happened would be noise. That stamping is also what keeps a single result
    from being counted here again on every subsequent run — a plan already
    marked skipped is excluded below, same as one already sent or already sat.
    """
    missed = []
    for plan in plans:
        if _resolved(plan):
            continue
        if plan["scheduled_for"] <= now:
            missed.append(plan)
    return missed
