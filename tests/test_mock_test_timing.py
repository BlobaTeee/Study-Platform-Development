"""Whether a mock test is still accepting answers."""
import importlib.util
from datetime import datetime, timedelta, timezone as tz
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "quizzes" / "services" / "timing.py")


def _load():
    spec = importlib.util.spec_from_file_location("timing_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


timing = _load()
START = datetime(2026, 7, 27, 10, 0, tzinfo=tz.utc)


def test_answers_are_open_at_the_start():
    assert timing.answers_are_open(START, 30, START) is True


def test_answers_are_open_just_before_the_deadline():
    assert timing.answers_are_open(START, 30, START + timedelta(minutes=29, seconds=59)) is True


def test_answers_close_exactly_at_the_deadline():
    # The deadline is the end of the allowed time, not one more second of it.
    assert timing.answers_are_open(START, 30, START + timedelta(minutes=30)) is False


def test_answers_are_closed_after_the_deadline():
    assert timing.answers_are_open(START, 30, START + timedelta(minutes=31)) is False


def test_a_zero_duration_test_is_never_open():
    assert timing.answers_are_open(START, 0, START) is False


def test_seconds_remaining_never_goes_negative():
    assert timing.seconds_remaining(START, 30, START + timedelta(minutes=99)) == 0


def test_seconds_remaining_counts_down():
    assert timing.seconds_remaining(START, 30, START + timedelta(minutes=10)) == 1200
