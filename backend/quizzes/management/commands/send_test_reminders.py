"""Send reminders for planned tests whose lead time has arrived.

Run on a schedule (cron or launchd), e.g. every fifteen minutes:

    */15 * * * * cd /path/to/backend && ./venv/bin/python manage.py send_test_reminders

Safe to run as often as you like: each plan's `reminder_sent_at` is stamped as
it is sent, so a second run finds nothing to do.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from quizzes.models import PlannedTest
from quizzes.services.reminder_email import build_reminder
from quizzes.services.reminders import due_reminders, missed_reminders
from users.timezones import zone_for

# Backends that accept a message without actually delivering it anywhere a
# recipient would see it. A deployment that forgets to set EMAIL_HOST falls
# back to the console backend (see settings.py) — send_mail() then never
# raises, so without this check the command would happily stamp every
# reminder as sent while every one of them just went to stdout, which cron
# throws away. dummy/locmem are the same story for tests and local dev.
NON_DELIVERING_EMAIL_BACKENDS = {
    'django.core.mail.backends.console.EmailBackend',
    'django.core.mail.backends.dummy.EmailBackend',
    'django.core.mail.backends.locmem.EmailBackend',
}


class _Stamped:
    """Prefix every line with the run's time.

    The command runs from a scheduler into a log file. A line like "Sent 1
    reminder(s)." with no time next to it cannot be matched to the plan it
    was about, which is what made a silent SMTP failure take an afternoon
    to date.
    """
    def __init__(self, wrapped, stamp):
        self._wrapped, self._stamp = wrapped, stamp

    def write(self, msg='', *args, **kwargs):
        self._wrapped.write(f'{self._stamp} {msg}', *args, **kwargs)


class Command(BaseCommand):
    help = 'Email reminders for planned tests whose lead time has arrived.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be sent without sending, stamping, or skipping.')

    def handle(self, *args, **options):
        now = timezone.now()
        dry_run = options['dry_run']
        stamp = timezone.localtime(now).strftime('%Y-%m-%d %H:%M:%S')
        self.stdout = _Stamped(self.stdout, stamp)
        self.stderr = _Stamped(self.stderr, stamp)

        # reminder_skipped_at__isnull=True bounds this query: without it, a
        # single plan a cron outage (or a userless email) has stamped skipped
        # would be re-loaded and re-reported on literally every future run,
        # forever. Excluding it here is what makes that stamp actually stick.
        candidates = list(
            PlannedTest.objects.filter(
                reminder_sent_at__isnull=True,
                reminder_skipped_at__isnull=True,
            ).select_related('user', 'user__profile', 'notebook')
        )
        rows = [{
            'id': plan.id,
            'scheduled_for': plan.scheduled_for,
            'reminder_lead_hours': plan.reminder_lead_hours,
            'reminder_sent_at': plan.reminder_sent_at,
            'reminder_skipped_at': plan.reminder_skipped_at,
            # Both fields, not just mock_test_id: mock_test is a OneToOneField
            # with on_delete=SET_NULL, so a deleted sitting would revert it to
            # NULL and make an already-taken test look unsat again. sat_at is
            # stamped once and never cleared, so it is what actually survives
            # the sitting being deleted.
            'taken': plan.sat_at is not None or plan.mock_test_id is not None,
        } for plan in candidates]

        by_id = {plan.id: plan for plan in candidates}
        due = [by_id[row['id']] for row in due_reminders(rows, now)]
        missed = [by_id[row['id']] for row in missed_reminders(rows, now)]

        # Terminal: a missed plan is stamped `reminder_skipped_at` so the
        # query above never loads it again, which is what turns this into a
        # "newly missed" count instead of a running total that only grows.
        # Never sent or stamped `reminder_sent_at` — a reminder for a test
        # that has already come and gone would be noise.
        if missed:
            if dry_run:
                self.stderr.write(
                    f'{len(missed)} planned test reminder(s) missed their window '
                    '(scheduled time passed before they were ever sent) — would '
                    'be marked skipped so this is reported once, not every run '
                    '(dry run: nothing written). Check whether the reminder cron '
                    'job has been running.')
            else:
                for plan in missed:
                    plan.reminder_skipped_at = now
                    plan.save(update_fields=['reminder_skipped_at'])
                self.stderr.write(
                    f'{len(missed)} planned test reminder(s) missed their window '
                    '(scheduled time passed before they were ever sent) — marked '
                    'skipped so this is reported once, not every run. Check '
                    'whether the reminder cron job has been running.')

        if not due:
            self.stdout.write('No reminders due.')
            return

        sent = 0
        skipped_no_email = 0
        skipped_undelivered = 0
        for plan in due:
            recipient = (plan.user.email or '').strip()
            if not recipient:
                self.stderr.write(f'Plan {plan.id}: user has no email address.')
                if dry_run:
                    self.stderr.write(
                        f'Plan {plan.id}: would be marked skipped (dry run).')
                else:
                    # Terminal, same as a missed window: an address that is
                    # empty today will not appear tomorrow on its own, so
                    # leaving reminder_sent_at/reminder_skipped_at both NULL
                    # would just make this plan reappear in `due` on every
                    # run for the rest of its lead window, and then in
                    # `missed` forever after that.
                    plan.reminder_skipped_at = now
                    plan.save(update_fields=['reminder_skipped_at'])
                    skipped_no_email += 1
                continue

            subject, body = build_reminder(
                notebook_title=plan.notebook.title,
                scheduled_for=timezone.localtime(plan.scheduled_for, zone_for(plan.user)),
                question_count=plan.question_count,
                duration_minutes=plan.duration_minutes,
                url=f'{settings.FRONTEND_URL}/dashboard/tests',
            )

            if dry_run:
                self.stdout.write(f'Would send to {recipient}: {subject}')
                continue

            try:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])
            except Exception as exc:  # noqa: BLE001
                # One unreachable recipient must not abort the batch, and the
                # plan stays unstamped so the next run tries again.
                self.stderr.write(f'Plan {plan.id}: send failed ({exc}).')
                continue

            if settings.EMAIL_BACKEND in NON_DELIVERING_EMAIL_BACKENDS:
                # send_mail() above did not raise, but nothing was actually
                # delivered anywhere a student would see it — stamping
                # reminder_sent_at here would permanently (and falsely) mark
                # this reminder as handled. Leave it unstamped so a future
                # run, once EMAIL_HOST is set, can actually send it.
                self.stderr.write(
                    f'Plan {plan.id}: reminder printed via '
                    f'{settings.EMAIL_BACKEND}, not delivered (no real mail '
                    'backend configured) — left unsent for a future run.')
                skipped_undelivered += 1
                continue

            plan.reminder_sent_at = timezone.now()
            plan.save(update_fields=['reminder_sent_at'])
            sent += 1

        self.stdout.write(f'Sent {sent} reminder(s).')
        if skipped_undelivered:
            self.stdout.write(
                f'{skipped_undelivered} reminder(s) printed but not delivered '
                f'(EMAIL_BACKEND={settings.EMAIL_BACKEND}) — left unsent for a '
                'future run.')
        if skipped_no_email:
            self.stdout.write(
                f'{skipped_no_email} reminder(s) skipped permanently (user has '
                'no email address).')
