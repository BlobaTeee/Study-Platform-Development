"""REST for live rounds: every step is a call, and the room hears about it
over the socket (room live-<id>). The views only translate; the rules are in
services/rounds.py."""
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notebooks.models import Notebook
from notebooks.realtime import emit_to_room as broadcast
from notebooks.services.membership import notebooks_for

from .models import LiveSession
from .services import rounds


def room_name(session) -> str:
    return f'live-{session.id}'


def _announce(session) -> None:
    broadcast(room_name(session), 'live:state', rounds.public_state(session))


def _summary(session, viewer=None) -> dict:
    """A room in a list. `joined` is the viewer's own; a broadcast leaves it out."""
    in_room = rounds.players(session)
    row = {'id': session.id, 'status': session.status,
           'notebook': {'id': session.notebook_id, 'title': session.notebook.title},
           'host': {'user_id': session.host_id, 'name': rounds._name(session.host)},
           'players': in_room.count()}
    if viewer is not None:
        row['joined'] = in_room.filter(user=viewer).exists()
    return row


def _refused(exc) -> Response:
    if isinstance(exc, rounds.NotAllowed):
        return Response({'detail': str(exc)}, status=403)
    if isinstance(exc, rounds.Conflict):
        return Response({'detail': str(exc)}, status=409)
    return Response({'detail': str(exc)}, status=400)


class RoomsView(APIView):
    """GET: the rooms open in my notebooks. POST {notebook, question_count?,
    seconds?}: open one, or join the one already open there."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = rounds.still_open(LiveSession.objects.filter(notebook__in=notebooks_for(request.user)))
        return Response({'rooms': [_summary(s, request.user) for s in sessions.select_related('notebook', 'host')]})

    def post(self, request):
        notebook = get_object_or_404(notebooks_for(request.user), pk=request.data.get('notebook'))
        try:
            session, created = rounds.open_room(request.user, notebook,
                                                request.data.get('question_count'), request.data.get('seconds'))
        except rounds.NoQuestions:
            return Response({'detail': _('This notebook has no multiple-choice or true/false questions yet. '
                                         'Make a quiz first.'), 'no_questions': True}, status=400)
        except (rounds.NotAllowed, rounds.Conflict) as exc:
            return _refused(exc)
        _announce(session)
        if created:
            for room in rounds.member_rooms(notebook, exclude=request.user):
                broadcast(room, 'live:open', _summary(session))
        return Response(rounds.state_for(session, request.user), status=201 if created else 200)


class RoomView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        session = _visible(request, pk)
        return Response(rounds.state_for(session, request.user))


class RoomActionView(APIView):
    """POST join / start / answer {index, choice} / reveal / next {index} (a vote) / leave."""
    permission_classes = [IsAuthenticated]
    action = ''

    def post(self, request, pk):
        session = _visible(request, pk)
        was_open = session.status != 'finished'
        try:
            if self.action == 'join':
                rounds.join(session, request.user)
            elif self.action == 'start':
                rounds.start(session, request.user)
            elif self.action == 'answer':
                rounds.answer(session, request.user, _int(request.data.get('index')), request.data.get('choice'))
            elif self.action == 'reveal':
                rounds.maybe_reveal(session)
            elif self.action == 'next':
                rounds.vote_next(session, request.user, _int(request.data.get('index')))
            elif self.action == 'leave':
                rounds.leave(session, request.user)
        except (rounds.NotAllowed, rounds.Conflict, rounds.Invalid) as exc:
            return _refused(exc)
        session.refresh_from_db()
        _announce(session)
        if was_open and session.status == 'finished':
            for room in rounds.member_rooms(session.notebook):
                broadcast(room, 'live:closed', {'id': session.id})
        return Response(rounds.state_for(session, request.user))


def _visible(request, pk) -> LiveSession:
    return get_object_or_404(LiveSession.objects.select_related('notebook', 'host')
                             .filter(notebook__in=notebooks_for(request.user)), pk=pk)


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1
