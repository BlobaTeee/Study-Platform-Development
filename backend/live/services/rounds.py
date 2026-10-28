"""The rules of a live round, whoever calls them.

A round is a fixed list of the notebook's questions, shown to everyone at
once. The server's clock decides what is late; nothing runs in the
background: when the time is up a client asks for the reveal (or, on a
reveal, repeats its vote once the majority rule applies) and the clock is
checked then. Every step that has already happened is a no-op, so two
players pressing at the same moment move the round on once.
"""
from __future__ import annotations

import random
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from notebooks.services.membership import is_member, members_of
from quizzes.models import Question
from quizzes.services.paper import _answer_matches

from ..models import LiveAnswer, LiveParticipant, LiveSession, LiveVote

OPEN = ('lobby', 'question', 'reveal')
# Typed answers need the AI grader; a live round must work without quota.
USABLE_TYPES = ('multiple_choice', 'true_false')
SECONDS_CHOICES = (15, 20, 30, 60)
DEFAULT_SECONDS = 20
DEFAULT_COUNT = 10
MAX_COUNT = 20
# For the network: an answer sent in the last second still counts.
GRACE = timedelta(seconds=2)
# The room moves on when everyone has voted for the next question, or, once
# the reveal has been up this long, when more than half have: someone who
# walked off does not hold the others.
MAJORITY_AFTER = timedelta(seconds=30)
# A room nobody has touched for this long was abandoned, not paused.
IDLE_LIMIT = timedelta(hours=2)


class NotAllowed(Exception):
    pass


class Conflict(Exception):
    pass


class Invalid(Exception):
    pass


class NoQuestions(Exception):
    pass


# ---- choosing the questions ------------------------------------------------------

def usable_question_ids(notebook) -> list[int]:
    return list(Question.objects
                .filter(quiz__is_published=True, quiz__sources__notebook=notebook,
                        question_type__in=USABLE_TYPES)
                .exclude(options=[])
                .values_list('id', flat=True).distinct().order_by('id'))


def owed_by_group(notebook, pool: list[int]) -> set[int]:
    """Questions any member still owes: the group's weak spots."""
    from quizzes.views import _owed_question_ids     # the one place the rule is assembled
    owed: set[int] = set()
    for member in members_of(notebook):
        owed |= _owed_question_ids(member.user, notebook)
    return owed & set(pool)


def choose_questions(pool: list[int], owed: set[int], count: int, rng=random) -> list[int]:
    """The group's misses first, the rest at random, `count` in all."""
    first = [q for q in pool if q in owed]
    rest = [q for q in pool if q not in owed]
    rng.shuffle(first)
    rng.shuffle(rest)
    return (first + rest)[:count]


def _clamp(value, choices=None, low=1, high=MAX_COUNT, default=DEFAULT_COUNT) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if choices:
        return n if n in choices else default
    return max(low, min(high, n))


# ---- opening, joining, leaving ---------------------------------------------------

def still_open(sessions):
    """The open ones among `sessions`, an abandoned one closed on the way."""
    now = timezone.now()
    sessions.filter(status__in=OPEN, updated_at__lt=now - IDLE_LIMIT).update(status='finished', finished_at=now)
    return sessions.filter(status__in=OPEN)


def open_rooms(notebook):
    return still_open(LiveSession.objects.filter(notebook=notebook))


def open_room(user, notebook, count=None, seconds=None) -> tuple[LiveSession, bool]:
    """The notebook's open room, joined; or a new one with `user` hosting."""
    if not is_member(notebook, user):
        raise NotAllowed('not in this notebook')
    with transaction.atomic():
        existing = open_rooms(notebook).select_for_update().first()
        if existing:
            join(existing, user)
            return existing, False
        pool = usable_question_ids(notebook)
        if not pool:
            raise NoQuestions('no multiple-choice or true/false questions yet')
        chosen = choose_questions(pool, owed_by_group(notebook, pool), _clamp(count))
        session = LiveSession.objects.create(
            notebook=notebook, host=user, question_ids=chosen,
            seconds=_clamp(seconds, choices=SECONDS_CHOICES, default=DEFAULT_SECONDS))
        LiveParticipant.objects.create(session=session, user=user)
    return session, True


def can_see(session, user) -> bool:
    return is_member(session.notebook, user)


def may_watch(user_id, session_id) -> bool:
    """Whether this person may receive a round's changes over the socket."""
    from django.contrib.auth.models import User
    session = LiveSession.objects.select_related('notebook').filter(pk=session_id).first()
    user = User.objects.filter(pk=user_id).first()
    return bool(session and user and can_see(session, user))


def join(session, user) -> None:
    if not can_see(session, user):
        raise NotAllowed('not in this notebook')
    if session.status == 'finished':
        raise Conflict('this room has closed')
    seat, made = LiveParticipant.objects.get_or_create(session=session, user=user)
    if not made and seat.left_at:
        seat.left_at = None
        seat.save(update_fields=['left_at'])
    session.save(update_fields=['updated_at'])


def players(session):
    return LiveParticipant.objects.filter(session=session, left_at__isnull=True).select_related('user')


def leave(session, user) -> None:
    """Out of the room. A host who leaves hands the room on; the last one out
    closes it; a player who left no longer holds up the reveal."""
    LiveParticipant.objects.filter(session=session, user=user, left_at__isnull=True).update(left_at=timezone.now())
    if session.status == 'finished':
        return
    remaining = list(players(session))
    if not remaining:
        _finish(session)
        return
    if session.host_id == user.id:
        session.host = remaining[0].user
        session.save(update_fields=['host', 'updated_at'])
    maybe_reveal(session)
    maybe_move_on(session)


# ---- the round -------------------------------------------------------------------

def start(session, user) -> None:
    if session.host_id != user.id:
        raise NotAllowed('only the host starts the round')
    if session.status != 'lobby':
        return
    _show(session, 0)


def current_question(session) -> Question | None:
    if session.status not in ('question', 'reveal') or session.index >= len(session.question_ids):
        return None
    return Question.objects.filter(pk=session.question_ids[session.index]).select_related('source').first()


def deadline(session):
    return session.question_started_at + timedelta(seconds=session.seconds)


def answer(session, user, index, choice) -> LiveAnswer:
    if not players(session).filter(user=user).exists():
        raise NotAllowed('join the room first')
    if session.status != 'question' or index != session.index:
        raise Conflict('that question is over')
    now = timezone.now()
    if now > deadline(session) + GRACE:
        raise Conflict('time is up')
    question = current_question(session)
    choice = str(choice or '').strip()
    if question is None or choice not in question.options:
        raise Invalid('not one of the options')
    with transaction.atomic():
        if LiveAnswer.objects.filter(session=session, user=user, index=index).exists():
            raise Conflict('already answered')
        given = LiveAnswer.objects.create(
            session=session, user=user, question=question, index=index, choice=choice,
            is_correct=_answer_matches(choice, question.correct_answer),
            ms=int((now - session.question_started_at).total_seconds() * 1000))
    maybe_reveal(session)
    return given


def maybe_reveal(session, now=None) -> bool:
    """Reveal the answer once everyone in the room has answered, or the time
    is up. Asked by any client when its countdown ends."""
    if session.status != 'question':
        return False
    now = now or timezone.now()
    in_room = set(players(session).values_list('user_id', flat=True))
    answered = set(LiveAnswer.objects.filter(session=session, index=session.index)
                   .values_list('user_id', flat=True))
    if now < deadline(session) and not in_room <= answered:
        return False
    updated = (LiveSession.objects.filter(pk=session.pk, status='question', index=session.index)
               .update(status='reveal', revealed_at=now, updated_at=now))
    session.refresh_from_db()
    return bool(updated)


def vote_next(session, user, index) -> None:
    """A vote to leave the reveal of question `index`. A vote for a question
    already past, or a second vote, changes nothing."""
    if not players(session).filter(user=user).exists():
        raise NotAllowed('join the room first')
    if session.status != 'reveal' or index != session.index:
        return
    LiveVote.objects.get_or_create(session=session, user=user, index=index)
    maybe_move_on(session)


def votes_for_next(session) -> list[int]:
    """Who in the room has voted to move on from this reveal."""
    in_room = players(session).values_list('user_id', flat=True)
    return sorted(LiveVote.objects.filter(session=session, index=session.index, user_id__in=in_room)
                  .values_list('user_id', flat=True))


def maybe_move_on(session, now=None) -> bool:
    """Everyone has voted; or the reveal has been up long enough and more than half have."""
    if session.status != 'reveal':
        return False
    now = now or timezone.now()
    voted = len(votes_for_next(session))
    in_room = players(session).count()
    everyone = in_room > 0 and voted >= in_room
    majority = voted * 2 > in_room and now >= session.revealed_at + MAJORITY_AFTER
    if not (everyone or majority):
        return False
    if session.index + 1 >= len(session.question_ids):
        _finish(session)
    else:
        _show(session, session.index + 1, expect=session.index)
    return True


def _show(session, index, expect=None) -> None:
    now = timezone.now()
    rows = LiveSession.objects.filter(pk=session.pk)
    rows = rows.filter(index=expect, status='reveal') if expect is not None else rows.filter(status='lobby')
    rows.update(status='question', index=index, question_started_at=now, revealed_at=None, updated_at=now)
    session.refresh_from_db()


def _finish(session) -> None:
    now = timezone.now()
    LiveSession.objects.filter(pk=session.pk).exclude(status='finished').update(
        status='finished', finished_at=now, updated_at=now)
    session.refresh_from_db()


# ---- what goes on the wire -------------------------------------------------------

def _name(user) -> str:
    return user.first_name or (user.email or '').split('@')[0] or 'Student'


def results(session) -> list[dict]:
    """Everyone who played, by score, ties to the faster."""
    rows: dict[int, dict] = {}
    for seat in LiveParticipant.objects.filter(session=session).select_related('user'):
        rows[seat.user_id] = {'user_id': seat.user_id, 'name': _name(seat.user), 'score': 0, 'ms': 0}
    for a in LiveAnswer.objects.filter(session=session):
        row = rows.get(a.user_id)
        if row:
            row['score'] += int(a.is_correct)
            row['ms'] += a.ms
    ranked = sorted(rows.values(), key=lambda r: (-r['score'], r['ms']))
    for i, row in enumerate(ranked):
        row['rank'] = i + 1
    return ranked


def public_state(session, now=None) -> dict:
    """The room as everyone sees it. The right answer is only in it after the
    reveal, so a payload in the browser cannot give it away."""
    now = now or timezone.now()
    in_room = list(players(session))
    question = current_question(session)
    answers = list(LiveAnswer.objects.filter(session=session, index=session.index)) if question else []
    answered_ids = {a.user_id for a in answers}
    scores = {r['user_id']: r['score'] for r in results(session)}

    state = {
        'id': session.id,
        'notebook': {'id': session.notebook_id, 'title': session.notebook.title},
        'host': {'user_id': session.host_id, 'name': _name(session.host)},
        'status': session.status,
        'index': session.index,
        'total': len(session.question_ids),
        'seconds': session.seconds,
        'players': [{'user_id': p.user_id, 'name': _name(p.user), 'score': scores.get(p.user_id, 0),
                     'answered': p.user_id in answered_ids} for p in in_room],
        'question': None,
        'remaining_ms': 0,
        'answered_count': len(answered_ids),
        'reveal': None,
        'voters': [],
        'next_votes': 0,
        'majority_in_ms': 0,
        'results': results(session) if session.status == 'finished' else [],
    }
    if question:
        state['question'] = {'id': question.id, 'text': question.question_text,
                             'type': question.question_type, 'options': list(question.options)}
    if session.status == 'question':
        state['remaining_ms'] = max(0, int((deadline(session) - now).total_seconds() * 1000))
    if session.status == 'reveal' and question:
        counts = {option: 0 for option in question.options}
        for a in answers:
            counts[a.choice] = counts.get(a.choice, 0) + 1
        state['reveal'] = {
            'correct': question.correct_answer,
            'counts': counts,
            'right': sorted(a.user_id for a in answers if a.is_correct),
            'explanation': question.explanation or '',
            'source_title': question.source.title if question.source else '',
            'source_excerpt': question.source_excerpt or '',
        }
        state['voters'] = votes_for_next(session)
        state['next_votes'] = len(state['voters'])
        state['majority_in_ms'] = max(0, int((session.revealed_at + MAJORITY_AFTER - now).total_seconds() * 1000))
    return state


def state_for(session, user) -> dict:
    """The room as one player sees it: the public state plus their own seat."""
    state = public_state(session)
    mine = {a.index: a for a in LiveAnswer.objects.filter(session=session, user=user).select_related('question')}
    current = mine.get(session.index) if session.status in ('question', 'reveal') else None
    you = {
        'user_id': user.id,
        'is_host': session.host_id == user.id,
        'joined': players(session).filter(user=user).exists(),
        'answer': current.choice if current else None,
        'missed': [],
    }
    if session.status == 'finished':
        for i, qid in enumerate(session.question_ids):
            given = mine.get(i)
            if given and given.is_correct:
                continue
            q = given.question if given else Question.objects.filter(pk=qid).first()
            if q is None:
                continue
            you['missed'].append({'question_id': q.id, 'text': q.question_text,
                                  'your_answer': given.choice if given else '',
                                  'correct': q.correct_answer, 'explanation': q.explanation or ''})
    state['you'] = you
    return state


def member_rooms(notebook, exclude=None) -> list[str]:
    """The personal rooms of the notebook's members, for telling them a room opened."""
    from notebooks.services.chat import user_room
    return [user_room(m.user_id) for m in members_of(notebook) if m.user_id != getattr(exclude, 'id', None)]
