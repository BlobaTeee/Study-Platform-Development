"""The reminder email's wording."""
import importlib.util
from datetime import datetime
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "quizzes" / "services" / "reminder_email.py")


def _load():
    spec = importlib.util.spec_from_file_location("reminder_email_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


emails = _load()
WHEN = datetime(2026, 7, 30, 14, 0)


def _build():
    return emails.build_reminder(
        notebook_title="Biology",
        scheduled_for=WHEN,
        question_count=20,
        duration_minutes=30,
        url="http://localhost:3000/dashboard/tests",
    )


def test_the_subject_names_the_subject_studied():
    subject, _ = _build()
    assert "Biology" in subject


def test_the_subject_is_a_single_line():
    subject, _ = _build()
    assert "\n" not in subject


def test_the_body_carries_the_time_length_and_link():
    _, body = _build()
    assert "30 minutes" in body
    assert "20 questions" in body
    assert "http://localhost:3000/dashboard/tests" in body


def test_the_body_states_the_scheduled_day_and_time():
    _, body = _build()
    assert "30 July 2026" in body
    assert "14:00" in body


def test_the_wording_stays_plain():
    # The app's voice is calm and scholarly; a reminder must not nag or shout.
    subject, body = _build()
    assert "!" not in subject and "!" not in body
