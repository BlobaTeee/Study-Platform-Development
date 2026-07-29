"""Wording for the planned-test reminder.

Free of Django so the message can be tested without a mail backend, and so the
command that sends it stays a thin shell around this.
"""
from __future__ import annotations


def build_reminder(notebook_title: str, scheduled_for, question_count: int,
                   duration_minutes: int, url: str) -> tuple[str, str]:
    """The (subject, body) of a reminder for one planned test.

    Plain and specific: the student booked this themselves, so the mail only
    has to say what and when, and get out of the way.
    """
    # Collapse whitespace (including newlines) in the user-authored title:
    # it lands raw in the subject, where a stray newline is a header-injection
    # hazard and would make Django's SMTP backend refuse to send the mail.
    notebook_title = ' '.join(notebook_title.split())

    # %Z resolves to a zone abbreviation/offset for an aware datetime and to
    # '' for a naive one, so a plain conditional append handles both without
    # leaving a dangling separator on the naive path.
    zone = scheduled_for.strftime('%Z')
    when = scheduled_for.strftime('%d %B %Y at %H:%M').lstrip('0')
    if zone:
        when = f'{when} {zone}'

    subject = f'Your {notebook_title} mock test is coming up'
    body = (
        f'You planned a mock test on {notebook_title}.\n\n'
        f'When: {when}\n'
        f'Paper: {question_count} questions, {duration_minutes} minutes\n\n'
        f'Sit it here: {url}\n\n'
        f'— StudyFlow\n'
    )
    return subject, body
