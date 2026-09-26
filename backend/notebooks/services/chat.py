"""The group chat's rules, independent of how a message arrives.

The REST endpoint and the Socket.IO server both call this, so a message
posted either way is validated, stored and shaped the same.
"""
from __future__ import annotations

from notebooks.models import NotebookMessage
from notebooks.services.membership import is_member, notebooks_for

MAX_BODY_CHARS = 2000
HISTORY_LIMIT = 50


def room_for(notebook_id: int) -> str:
    """The Socket.IO room a notebook's members share."""
    return f'notebook-{notebook_id}'


def rooms_for_user(user) -> list[str]:
    """Every room this person is entitled to join, newest notebook first."""
    return [room_for(nb_id) for nb_id in
            notebooks_for(user).order_by('-updated_at').values_list('id', flat=True)]


def post_message(notebook, user, body: str) -> NotebookMessage:
    """Store one message. Raises PermissionError for outsiders and
    ValueError for a body that is empty or too long."""
    if not is_member(notebook, user):
        raise PermissionError('not a member of this notebook')
    body = (body or '').strip()
    if not body:
        raise ValueError('empty message')
    if len(body) > MAX_BODY_CHARS:
        raise ValueError('message too long')
    return NotebookMessage.objects.create(notebook=notebook, user=user, body=body)


def message_payload(message, viewer=None) -> dict:
    """What a message looks like on the wire, for REST and the socket alike.

    `viewer` decides `is_you`; the socket broadcasts one payload to the whole
    room, so it leaves that out and the client compares user_id itself.
    """
    author = message.user
    payload = {
        'id': message.id,
        'notebook': message.notebook_id,
        'body': message.body,
        'created_at': message.created_at.isoformat(),
        'author': {
            'user_id': author.id,
            'name': author.first_name or (author.email or '').split('@')[0] or 'Student',
        },
    }
    if viewer is not None:
        payload['author']['is_you'] = author.id == viewer.id
    return payload


def history(notebook, viewer, limit: int = HISTORY_LIMIT, before: int | None = None) -> list[dict]:
    """The last `limit` messages, oldest first; `before` pages backwards."""
    qs = NotebookMessage.objects.filter(notebook=notebook).select_related('user')
    if before:
        qs = qs.filter(id__lt=before)
    rows = list(qs.order_by('-id')[:limit])
    rows.reverse()
    return [message_payload(m, viewer) for m in rows]
