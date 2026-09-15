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
    assert 'Biology' in subject and 'Sit it here' in body
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
