"""The reminder command against a real database and a stubbed mail send.

The which-plans-are-due rule is covered in ../tests/test_test_reminders.py;
this covers what the command does with the answer: stamping, skipping, and
refusing to pretend a console backend delivered anything."""
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from quizzes.models import PlannedTest

pytestmark = pytest.mark.django_db

SMTP = 'django.core.mail.backends.smtp.EmailBackend'
CONSOLE = 'django.core.mail.backends.console.EmailBackend'


def _plan(user, notebook, hours_ahead, lead=1):
    return PlannedTest.objects.create(
        user=user, notebook=notebook, question_count=5, duration_minutes=10,
        scheduled_for=timezone.now() + timedelta(hours=hours_ahead),
        reminder_lead_hours=lead)


@pytest.fixture
def sent(monkeypatch):
    """Capture send_mail calls instead of opening an SMTP connection."""
    calls = []
    monkeypatch.setattr('quizzes.management.commands.send_test_reminders.send_mail',
                        lambda *args, **kwargs: calls.append(args))
    return calls


def _run(*args):
    out, err = StringIO(), StringIO()
    call_command('send_test_reminders', *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_a_due_reminder_is_sent_to_the_users_email_and_stamped(settings, sent, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    plan = _plan(user, notebook, hours_ahead=0.5, lead=1)   # window opened 30 min ago

    out, _ = _run()

    assert 'Sent 1 reminder(s).' in out
    (subject, body, sender, recipients), = sent
    assert recipients == ['student@example.com']
    assert 'Biology' in subject and 'Làm bài tại' in body   # Vietnamese by default
    plan.refresh_from_db()
    assert plan.reminder_sent_at is not None


def test_a_second_run_does_not_send_again(settings, sent, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    _plan(user, notebook, hours_ahead=0.5)
    _run()

    out, _ = _run()

    assert len(sent) == 1
    assert 'No reminders due.' in out


def test_a_plan_whose_window_has_not_opened_is_left_alone(settings, sent, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    plan = _plan(user, notebook, hours_ahead=5, lead=1)

    _run()

    assert sent == []
    plan.refresh_from_db()
    assert plan.reminder_sent_at is None and plan.reminder_skipped_at is None


def test_a_plan_already_sat_is_never_reminded(settings, sent, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    plan = _plan(user, notebook, hours_ahead=0.5)
    PlannedTest.objects.filter(id=plan.id).update(sat_at=timezone.now())

    _run()

    assert sent == []


def test_a_window_that_closed_unsent_is_marked_skipped_once(settings, sent, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    plan = _plan(user, notebook, hours_ahead=-1)   # scheduled time already passed

    _, err = _run()
    _, err2 = _run()

    assert sent == []
    assert 'missed their window' in err
    assert 'missed their window' not in err2
    plan.refresh_from_db()
    assert plan.reminder_skipped_at is not None


def test_the_console_backend_does_not_count_as_delivered(settings, sent, user, notebook):
    # Without EMAIL_HOST Django prints mail to stdout. The plan must stay
    # unsent so a later run, once SMTP is configured, still delivers it.
    settings.EMAIL_BACKEND = CONSOLE
    plan = _plan(user, notebook, hours_ahead=0.5)

    out, err = _run()

    assert 'not delivered' in err
    plan.refresh_from_db()
    assert plan.reminder_sent_at is None


def test_a_user_with_no_email_is_skipped_permanently(settings, sent, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    user.email = ''
    user.save(update_fields=['email'])
    plan = _plan(user, notebook, hours_ahead=0.5)

    _, err = _run()

    assert 'no email address' in err
    assert sent == []
    plan.refresh_from_db()
    assert plan.reminder_skipped_at is not None


def test_a_failed_send_is_retried_next_run(settings, monkeypatch, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    plan = _plan(user, notebook, hours_ahead=0.5)
    def refuse(*args, **kwargs):
        raise OSError('535 bad credentials')
    monkeypatch.setattr('quizzes.management.commands.send_test_reminders.send_mail', refuse)

    _, err = _run()

    assert 'send failed' in err
    plan.refresh_from_db()
    assert plan.reminder_sent_at is None and plan.reminder_skipped_at is None


def test_dry_run_reports_without_sending_or_stamping(settings, sent, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    plan = _plan(user, notebook, hours_ahead=0.5)

    out, _ = _run('--dry-run')

    assert 'Would send to student@example.com' in out
    assert sent == []
    plan.refresh_from_db()
    assert plan.reminder_sent_at is None


# ---- the time in the mail is the student's, not the server's ----------------

def test_the_reminder_states_the_time_in_the_users_own_timezone(settings, sent, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    settings.TIME_ZONE = 'Asia/Ho_Chi_Minh'
    user.profile.timezone = 'Europe/London'
    user.profile.preferred_language = 'en'
    user.profile.save(update_fields=['timezone', 'preferred_language'])
    from datetime import datetime, timezone as tz
    plan = _plan(user, notebook, hours_ahead=0.5)
    # Pin the booked instant so the expected wall-clock time is exact:
    # 2026-09-16 14:00 UTC is 15:00 in London (BST) and 21:00 in Ho Chi Minh.
    PlannedTest.objects.filter(id=plan.id).update(
        scheduled_for=datetime(2026, 9, 16, 14, 0, tzinfo=tz.utc),
        reminder_lead_hours=72)
    monkey_now = datetime(2026, 9, 16, 13, 30, tzinfo=tz.utc)
    import quizzes.management.commands.send_test_reminders as cmd
    orig = cmd.timezone.now
    cmd.timezone.now = lambda: monkey_now
    try:
        _run()
    finally:
        cmd.timezone.now = orig

    (_, body, _, _), = sent
    assert 'When: 16 September 2026 at 15:00 BST' in body
    assert '21:00' not in body


def test_an_unknown_timezone_on_the_profile_falls_back_to_the_servers(settings, sent, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    settings.TIME_ZONE = 'Asia/Ho_Chi_Minh'
    from users.models import UserProfile
    UserProfile.objects.filter(user=user).update(timezone='Mars/Olympus_Mons')
    _plan(user, notebook, hours_ahead=0.5)

    _run()

    (_, body, _, _), = sent
    assert '+07' in body


# ---- the log can be read back later ------------------------------------------

def test_every_line_is_stamped_with_the_run_time(settings, sent, user, notebook):
    # The command runs from a scheduler into a log file; a line without a
    # time cannot be matched to the plan it was about.
    import re
    settings.EMAIL_BACKEND = SMTP
    _plan(user, notebook, hours_ahead=0.5)
    _plan(user, notebook, hours_ahead=-1)   # also produces a stderr line

    out, err = _run()

    lines = [l for l in (out + err).splitlines() if l.strip()]
    assert lines, 'expected some output'
    assert all(re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ', l) for l in lines), lines


def test_an_english_profile_gets_the_english_reminder(settings, sent, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    user.profile.preferred_language = 'en'
    user.profile.save(update_fields=['preferred_language'])
    _plan(user, notebook, hours_ahead=0.5)

    _run()

    (subject, body, _, _), = sent
    assert 'Bài tự kiểm tra' not in subject
    assert 'Sit it here' in body
