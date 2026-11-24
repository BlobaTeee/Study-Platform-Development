"""Which model answers first.

Two lanes. Writing study material (cards, questions, problems, key points,
reading a photo) goes to the strongest model first, because quality is what
the student keeps. A short judgement the student is waiting on (grading an
answer, a hint, "why is this wrong?", the card tutor, feedback on an
explanation, naming a group of mistakes) goes to the fast model first: on the
same grading prompt gemini-3.1-flash-lite answered in about 6 s while the
stronger models sat for 28 s and timed out. Each lane falls back to the
other's model, so the two cover for each other.

Set per call with `with quick(): ...` rather than a parameter, so every
provider (Gemini, Ollama, test fakes) keeps the same `generate_json(prompt)`
signature; only the Gemini client reads the lane.
"""
import time
from contextlib import contextmanager
from contextvars import ContextVar

_QUICK: ContextVar[bool] = ContextVar('gemini_quick_lane', default=False)


@contextmanager
def quick():
    """Run the model calls inside on the quick lane."""
    token = _QUICK.set(True)
    try:
        yield
    finally:
        _QUICK.reset(token)


def is_quick() -> bool:
    return _QUICK.get()


# Reading a photo or a many-page file: one request whose answer is long (a
# nine-page scanned exam came back in 11 s once and ran past 30 s the next
# time), so it is given longer before it counts as stuck.
_LONG: ContextVar[bool] = ContextVar('gemini_long_read', default=False)
# Copying a file out is transcription, so it thinks less. Writing several
# answer keys at once is long too, but solving needs the thinking: it keeps it.
_THINK_LESS: ContextVar[bool] = ContextVar('gemini_long_think_less', default=True)


@contextmanager
def long_read(think_less: bool = True):
    token, thinking = _LONG.set(True), _THINK_LESS.set(think_less)
    try:
        yield
    finally:
        _LONG.reset(token)
        _THINK_LESS.reset(thinking)


def is_long() -> bool:
    return _LONG.get()


def thinks_less() -> bool:
    return _LONG.get() and _THINK_LESS.get()


# How long one piece of work may wait on the AI in all: every model in the
# fallback chain and any retry together. Each model alone may take up to its
# own deadline, and on 2026-11-23, with Gemini overloaded, one answer key went
# through the chain for over five minutes before saying so; a clear "try again"
# after a minute and a half serves the student better.
_DEADLINE: ContextVar[float | None] = ContextVar('gemini_deadline', default=None)


def budget_seconds(quick: bool = False, long: bool = False) -> float:
    """The total wait for one piece of work on its lane."""
    from django.conf import settings
    if long:
        return float(getattr(settings, 'GEMINI_READ_TOTAL_SECONDS', 200))
    if quick:
        return float(getattr(settings, 'GEMINI_FAST_TOTAL_SECONDS', 30))
    return float(getattr(settings, 'GEMINI_TOTAL_SECONDS', 90))


@contextmanager
def within(seconds: float):
    """Every model call inside shares `seconds` (or less, inside an earlier
    `within`)."""
    end = time.monotonic() + seconds
    current = _DEADLINE.get()
    token = _DEADLINE.set(end if current is None else min(current, end))
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def seconds_left() -> float | None:
    """Seconds left inside `within`, or None outside one."""
    end = _DEADLINE.get()
    return None if end is None else end - time.monotonic()
