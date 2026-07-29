"""Whether a mock test's clock has run out.

Kept separate from the view and free of Django so the boundary condition — the
one thing a timed test must get right — can be tested directly. The client
renders a countdown, but only this decides whether an answer arrived in time:
a timer in the browser is changed by anyone who opens the developer tools.
"""
from __future__ import annotations

from datetime import timedelta


def deadline_for(started_at, duration_minutes: int):
    """When the paper stops accepting answers."""
    return started_at + timedelta(minutes=duration_minutes)


def answers_are_open(started_at, duration_minutes: int, now) -> bool:
    """True while the paper is still within its allotted time.

    The deadline itself is closed: a test with thirty minutes gets thirty
    minutes, not thirty minutes and one more answer.
    """
    return now < deadline_for(started_at, duration_minutes)


def seconds_remaining(started_at, duration_minutes: int, now) -> int:
    """Whole seconds left, never negative — an overrun is simply out of time."""
    remaining = (deadline_for(started_at, duration_minutes) - now).total_seconds()
    return max(0, int(remaining))
