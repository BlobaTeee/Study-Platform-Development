"""The group chat's rules, independent of how a message arrives.

The REST endpoint and the Socket.IO server both call this, so a message
posted either way is validated, stored and shaped the same.
"""
from __future__ import annotations

from django.db.models import Q

from notebooks.models import ChatGroup, ChatGroupMember, DirectMessage, GroupMessage
from notebooks.services.membership import notebooks_for

MAX_BODY_CHARS = 2000
HISTORY_LIMIT = 50


def room_for(group_id: int) -> str:
    """The Socket.IO room a chat group's members share."""
    return f'group-{group_id}'


def rooms_for_user(user) -> list[str]:
    """Every room this person is entitled to join."""
    return [room_for(gid) for gid in
            ChatGroupMember.objects.filter(user=user).values_list('group_id', flat=True)]


def groups_for(user):
    """The chat groups this person is in, most recently created first."""
    return ChatGroup.objects.filter(members__user=user).distinct()


def in_group(group, user) -> bool:
    return ChatGroupMember.objects.filter(group=group, user=user).exists()


def create_group(creator, name: str, member_ids: list[int]) -> ChatGroup:
    """A new group. The maker is always in it; everyone else must be someone
    they already share study material with, so a group cannot be used to
    reach a stranger."""
    from django.contrib.auth.models import User

    name = (name or '').strip()
    if not name:
        raise ValueError('a group needs a name')
    if len(name) > 120:
        raise ValueError('name too long')
    others = list(User.objects.filter(id__in=set(member_ids) - {creator.id}))
    for person in others:
        if not can_message(creator, person):
            raise PermissionError(f'{person.id} shares no notebook with you')
    group = ChatGroup.objects.create(name=name, created_by=creator)
    ChatGroupMember.objects.bulk_create(
        [ChatGroupMember(group=group, user=creator)]
        + [ChatGroupMember(group=group, user=p) for p in others],
        ignore_conflicts=True,
    )
    return group


def add_member(group, actor, person) -> None:
    """Anyone in the group may bring in someone they study with."""
    if not in_group(group, actor):
        raise PermissionError('not in this group')
    if not can_message(actor, person):
        raise PermissionError('you share no notebook with this person')
    ChatGroupMember.objects.get_or_create(group=group, user=person)


def post_message(group, user, body: str) -> GroupMessage:
    """Store one message. Raises PermissionError for outsiders and
    ValueError for a body that is empty or too long."""
    if not in_group(group, user):
        raise PermissionError('not in this group')
    body = (body or '').strip()
    if not body:
        raise ValueError('empty message')
    if len(body) > MAX_BODY_CHARS:
        raise ValueError('message too long')
    return GroupMessage.objects.create(group=group, user=user, body=body)


def message_payload(message, viewer=None) -> dict:
    """What a message looks like on the wire, for REST and the socket alike.

    `viewer` decides `is_you`; the socket broadcasts one payload to the whole
    room, so it leaves that out and the client compares user_id itself.
    """
    author = message.user
    payload = {
        'id': message.id,
        'group': message.group_id,
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


def history(group, viewer, limit: int = HISTORY_LIMIT, before: int | None = None) -> list[dict]:
    """The last `limit` messages, oldest first; `before` pages backwards."""
    qs = GroupMessage.objects.filter(group=group).select_related('user')
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
    """What the chat launcher lists: the groups you are in, and the people
    you share study material with."""
    from notebooks.models import NotebookMember

    groups = []
    for group in groups_for(viewer).order_by('-id'):
        last = GroupMessage.objects.filter(group=group).select_related('user').order_by('-id').first()
        groups.append({
            'id': group.id,
            'name': group.name,
            'members': ChatGroupMember.objects.filter(group=group).count(),
            'last': _last_line(last, last.user if last else None, viewer),
        })
    groups.sort(key=lambda g: (g['last'] or {}).get('id', 0), reverse=True)

    # Everyone you share a notebook with: the people you may write to.
    people_ids = (NotebookMember.objects
                  .filter(notebook__in=notebooks_for(viewer))
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
