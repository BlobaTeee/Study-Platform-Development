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


class Command(BaseCommand):
    help = 'Email reminders for planned tests whose lead time has arrived.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be sent without sending or stamping.')

    def handle(self, *args, **options):
        now = timezone.now()
        candidates = list(
            PlannedTest.objects.filter(reminder_sent_at__isnull=True)
            .select_related('user', 'notebook')
        )
        rows = [{
            'id': plan.id,
            'scheduled_for': plan.scheduled_for,
            'reminder_lead_hours': plan.reminder_lead_hours,
            'reminder_sent_at': plan.reminder_sent_at,
            # Both fields, not just mock_test_id: mock_test is a OneToOneField
            # with on_delete=SET_NULL, so a deleted sitting would revert it to
            # NULL and make an already-taken test look unsat again. sat_at is
            # stamped once and never cleared, so it is what actually survives
            # the sitting being deleted.
            'taken': plan.sat_at is not None or plan.mock_test_id is not None,
        } for plan in candidates]

        by_id = {plan.id: plan for plan in candidates}
        due = [by_id[row['id']] for row in due_reminders(rows, now)]

        # Reporting-only: a plan here means its whole lead window passed
        # with cron never sending it, and nothing else anywhere would
        # otherwise show that. Surfacing the count on stderr is what makes a
        # cron outage visible instead of the student just never hearing
        # about their test. Never send or stamp these — a reminder for a
        # test that has already come and gone is noise.
        missed = missed_reminders(rows, now)
        if missed:
            self.stderr.write(
                f'{len(missed)} planned test reminder(s) missed their window '
                '(scheduled time passed before they were ever sent) — check '
                'whether the reminder cron job has been running.')

        if not due:
            self.stdout.write('No reminders due.')
            return

        sent = 0
        for plan in due:
            recipient = (plan.user.email or '').strip()
            if not recipient:
                # Nothing to send to. Stamping anyway would silently swallow the
                # reminder, so it is left for when the account has an address.
                self.stderr.write(f'Plan {plan.id}: user has no email address; skipped.')
                continue

            subject, body = build_reminder(
                notebook_title=plan.notebook.title,
                scheduled_for=timezone.localtime(plan.scheduled_for),
                question_count=plan.question_count,
                duration_minutes=plan.duration_minutes,
                url=f'{settings.FRONTEND_URL}/dashboard/tests',
            )

            if options['dry_run']:
                self.stdout.write(f'Would send to {recipient}: {subject}')
                continue

            try:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])
            except Exception as exc:  # noqa: BLE001
                # One unreachable recipient must not abort the batch, and the
                # plan stays unstamped so the next run tries again.
                self.stderr.write(f'Plan {plan.id}: send failed ({exc}).')
                continue

            plan.reminder_sent_at = timezone.now()
            plan.save(update_fields=['reminder_sent_at'])
            sent += 1

        self.stdout.write(f'Sent {sent} reminder(s).')
