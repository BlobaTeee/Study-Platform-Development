"""Inviting someone into a notebook.

Keyed on an email address rather than a user: the person invited may not
have an account yet, and the link is what they bring back. One live
invitation per address per notebook, so pressing invite twice hands over
the same link instead of scattering tokens.
"""
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from notebooks.models import NotebookInvite, NotebookMember

TOKEN_BYTES = 32          # 43 URL-safe characters


class InviteError(Exception):
    """The link cannot be used, with a sentence saying why."""


def invite_url(token: str) -> str:
    return f'{settings.FRONTEND_URL}/join/{token}'


def create_invite(notebook, inviter, email: str) -> NotebookInvite:
    email = email.strip().lower()
    invite = NotebookInvite.objects.filter(
        notebook=notebook, email=email, accepted_at__isnull=True).first()
    if invite is None:
        invite = NotebookInvite.objects.create(
            notebook=notebook, email=email, invited_by=inviter,
            token=secrets.token_urlsafe(TOKEN_BYTES),
        )
    return invite


def build_email(notebook_title: str, inviter_name: str, url: str, lang: str = 'en') -> tuple[str, str]:
    """(subject, body). Plain and short: the link is the point."""
    notebook_title = ' '.join(notebook_title.split())
    if lang == 'vi':
        return (
            f'{inviter_name} mời bạn vào sổ tay "{notebook_title}" trên StudyFlow',
            f'{inviter_name} đã mời bạn cùng học sổ tay "{notebook_title}".\n\n'
            f'Mở liên kết này để tham gia:\n{url}\n\n'
            'Bạn sẽ thấy tài liệu và bộ thẻ của sổ tay; tiến độ ôn tập của bạn là riêng.\n',
        )
    return (
        f'{inviter_name} invited you to "{notebook_title}" on StudyFlow',
        f'{inviter_name} invited you to study "{notebook_title}" together.\n\n'
        f'Open this link to join:\n{url}\n\n'
        'You will see the notebook\'s documents and decks; what you study stays your own.\n',
    )


def send_invite_email(invite, inviter_name: str, lang: str = 'en') -> bool:
    """True when the mail went out. A failure is not fatal: the inviter still
    has the link to send by hand, which is what the response carries."""
    subject, body = build_email(invite.notebook.title, inviter_name, invite_url(invite.token), lang)
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [invite.email], fail_silently=False)
        return True
    except Exception:  # noqa: BLE001 — SMTP down, no credentials, bad address
        return False


@transaction.atomic
def accept_invite(token: str, user) -> NotebookInvite:
    invite = NotebookInvite.objects.select_for_update().filter(token=token).first()
    if invite is None:
        raise LookupError
    if invite.accepted_at is not None:
        raise InviteError(_('This invitation has already been used. Ask for a new link.'))
    NotebookMember.objects.get_or_create(
        notebook=invite.notebook, user=user, defaults={'role': 'member'})
    invite.accepted_at = timezone.now()
    invite.accepted_by = user
    invite.save(update_fields=['accepted_at', 'accepted_by'])
    return invite
