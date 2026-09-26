"""The group chat's rules, independent of how a message arrives.

The REST endpoint and the Socket.IO server both call this, so a message
posted either way is validated, stored and shaped the same.
"""
from __future__ import annotations

from django.db.models import Q

from notebooks.models import DirectMessage, NotebookMessage
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


# ---- private threads ---------------------------------------------------------------

def user_room(user_id: int) -> str:
    """Every client joins the room of its own user, so a private message can
    be delivered to whichever devices that person has open."""
    return f'user-{user_id}'


def can_message(sender, recipient) -> bool:
    """You may write to someone you share a notebook with, and to nobody
    else: the app is a study tool, not an open inbox."""
    if sender.id == recipient.id:
        return False
    mine = set(notebooks_for(sender).values_list('id', flat=True))
    if not mine:
        return False
    return notebooks_for(recipient).filter(id__in=mine).exists()


def send_direct(sender, recipient, body: str) -> DirectMessage:
    """Store one private message. PermissionError when the two share
    nothing; ValueError for an empty or oversized body."""
    if not can_message(sender, recipient):
        raise PermissionError('you cannot message this person')
    body = (body or '').strip()
    if not body:
        raise ValueError('empty message')
    if len(body) > MAX_BODY_CHARS:
        raise ValueError('message too long')
    return DirectMessage.objects.create(sender=sender, recipient=recipient, body=body)


def direct_payload(message, viewer=None) -> dict:
    author = message.sender
    payload = {
        'id': message.id,
        'with': message.recipient_id if viewer and viewer.id == author.id else author.id,
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


def direct_history(viewer, other, limit: int = HISTORY_LIMIT, before: int | None = None) -> list[dict]:
    """The thread between two people, oldest last, paging backwards."""
    qs = DirectMessage.objects.filter(
        Q(sender=viewer, recipient=other) | Q(sender=other, recipient=viewer)
    ).select_related('sender')
    if before:
        qs = qs.filter(id__lt=before)
    rows = list(qs.order_by('-id')[:limit])
    rows.reverse()
    return [direct_payload(m, viewer) for m in rows]


def chat_overview(viewer) -> dict:
    """What the chat launcher lists: the notebooks you are in, and the people
    you share them with, each with the last thing said."""
    from notebooks.models import NotebookMember

    notebooks = list(notebooks_for(viewer).order_by('-updated_at'))
    groups = []
    for nb in notebooks:
        last = (NotebookMessage.objects.filter(notebook=nb)
                .select_related('user').order_by('-id').first())
        groups.append({
            'notebook': nb.id,
            'title': nb.title,
            'members': NotebookMember.objects.filter(notebook=nb).count(),
            'last': _last_line(last, last.user if last else None, viewer),
        })

    # Everyone in those notebooks, once, minus yourself.
    people_ids = (NotebookMember.objects
                  .filter(notebook__in=notebooks)
                  .exclude(user=viewer)
                  .values_list('user_id', flat=True).distinct())
    people = []
    for other_id in people_ids:
        last = (DirectMessage.objects
                .filter(Q(sender=viewer, recipient_id=other_id) | Q(sender_id=other_id, recipient=viewer))
                .select_related('sender').order_by('-id').first())
        member = NotebookMember.objects.filter(user_id=other_id).select_related('user').first()
        person = member.user
        people.append({
            'user_id': other_id,
            'name': person.first_name or (person.email or '').split('@')[0] or 'Student',
            'last': _last_line(last, last.sender if last else None, viewer),
        })
    # Whoever spoke most recently first; never-messaged people keep their order.
    people.sort(key=lambda p: (p['last'] or {}).get('id', 0), reverse=True)
    return {'groups': groups, 'people': people}


def _last_line(message, author, viewer) -> dict | None:
    if message is None:
        return None
    return {
        'id': message.id,
        'body': message.body,
        'created_at': message.created_at.isoformat(),
        'is_you': author is not None and author.id == viewer.id,
        'author': (author.first_name or 'Student') if author else '',
    }
