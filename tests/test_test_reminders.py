"""Which planned tests are owed a reminder right now."""
import importlib.util
from datetime import datetime, timedelta, timezone as tz
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "quizzes" / "services" / "reminders.py")


def _load():
    spec = importlib.util.spec_from_file_location("reminders_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


reminders = _load()
NOW = datetime(2026, 7, 27, 12, 0, tzinfo=tz.utc)


def _plan(**overrides):
    plan = {
        "id": 1,
        "scheduled_for": NOW + timedelta(hours=24),
        "reminder_lead_hours": 24,
        "reminder_sent_at": None,
        "reminder_skipped_at": None,
        "taken": False,
    }
    plan.update(overrides)
    return plan


def test_a_plan_exactly_at_its_lead_time_is_due():
    # 24h ahead with a 24h lead: the window opens now, to the second.
    assert [p["id"] for p in reminders.due_reminders([_plan()], NOW)] == [1]


def test_a_plan_still_beyond_its_lead_time_is_not_due():
    plan = _plan(scheduled_for=NOW + timedelta(hours=25))
    assert reminders.due_reminders([plan], NOW) == []


def test_a_plan_inside_its_lead_time_is_due():
    plan = _plan(scheduled_for=NOW + timedelta(hours=2))
    assert [p["id"] for p in reminders.due_reminders([plan], NOW)] == [1]


def test_a_plan_already_reminded_is_skipped():
    plan = _plan(reminder_sent_at=NOW - timedelta(hours=1))
    assert reminders.due_reminders([plan], NOW) == []


def test_a_plan_already_sat_is_skipped():
    assert reminders.due_reminders([_plan(taken=True)], NOW) == []


def test_a_test_whose_time_has_passed_is_skipped():
    # Reminding someone about a test they have already missed is noise.
    plan = _plan(scheduled_for=NOW - timedelta(minutes=1))
    assert reminders.due_reminders([plan], NOW) == []


def test_a_short_lead_holds_the_reminder_back():
    plan = _plan(scheduled_for=NOW + timedelta(hours=5), reminder_lead_hours=1)
    assert reminders.due_reminders([plan], NOW) == []
    later = NOW + timedelta(hours=4, minutes=1)
    assert [p["id"] for p in reminders.due_reminders([plan], later)] == [1]


def test_several_plans_are_filtered_independently():
    plans = [
        _plan(id=1),
        _plan(id=2, reminder_sent_at=NOW),
        _plan(id=3, scheduled_for=NOW + timedelta(days=9)),
    ]
    assert [p["id"] for p in reminders.due_reminders(plans, NOW)] == [1]


def test_a_plan_past_its_time_and_unsent_counts_as_missed():
    plan = _plan(scheduled_for=NOW - timedelta(minutes=1))
    assert [p["id"] for p in reminders.missed_reminders([plan], NOW)] == [1]


def test_a_missed_plan_already_sent_does_not_count():
    plan = _plan(scheduled_for=NOW - timedelta(minutes=1),
                  reminder_sent_at=NOW - timedelta(hours=1))
    assert reminders.missed_reminders([plan], NOW) == []


def test_a_missed_plan_already_taken_does_not_count():
    plan = _plan(scheduled_for=NOW - timedelta(minutes=1), taken=True)
    assert reminders.missed_reminders([plan], NOW) == []


def test_a_plan_still_in_the_future_does_not_count_as_missed():
    plan = _plan(scheduled_for=NOW + timedelta(hours=2))
    assert reminders.missed_reminders([plan], NOW) == []


# ---- reminder_skipped_at: a plan the command has already given up on -------
#
# The command stamps reminder_skipped_at (missed window, or user has no
# email) so that a single cron outage produces a "missed" count exactly once,
# not on every run forever after. That only works if a skipped plan is fully
# inert here: neither due, nor counted missed a second time.

def test_a_skipped_plan_is_not_due_even_within_its_lead_window():
    plan = _plan(scheduled_for=NOW + timedelta(hours=2),
                 reminder_skipped_at=NOW - timedelta(hours=1))
    assert reminders.due_reminders([plan], NOW) == []


def test_a_skipped_plan_whose_time_has_passed_does_not_count_as_missed_again():
    # Without this, a plan the previous run already reported (and stamped)
    # would be reported as missed again on this run, and every run after —
    # the exact unbounded-report bug reminder_skipped_at exists to close.
    plan = _plan(scheduled_for=NOW - timedelta(minutes=1),
                 reminder_skipped_at=NOW - timedelta(minutes=30))
    assert reminders.missed_reminders([plan], NOW) == []


def test_an_unskipped_plan_past_its_time_still_counts_as_missed():
    # Control for the test above: only the presence of reminder_skipped_at
    # should suppress the missed count, not merely being past scheduled_for.
    plan = _plan(scheduled_for=NOW - timedelta(minutes=1))
    assert [p["id"] for p in reminders.missed_reminders([plan], NOW)] == [1]
