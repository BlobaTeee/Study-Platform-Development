"""A live round played over the real wire: uvicorn, Socket.IO and HTTP.

The rules are covered in test_live_study.py with the broadcast stubbed out.
This one runs the ASGI app in a real server and plays a whole round with two
socket clients and plain HTTP calls, the way two browsers would, to show the
changes actually reach both players and the rules hold end to end. Only the
Supabase token check is replaced: "token-<id>" is that user.
"""
import asyncio
import socket
import threading
import time

import httpx
import pytest
import socketio
import uvicorn
from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed

from tests.test_live_study import _questions

pytestmark = pytest.mark.django_db(transaction=True)
WAIT = 8.0


@pytest.fixture
def server(monkeypatch):
    """The project's ASGI app (Socket.IO in front of Django) on a free port."""
    def fake_user_for_token(token):
        try:
            return get_user_model().objects.get(pk=int(str(token).removeprefix('token-')))
        except (ValueError, get_user_model().DoesNotExist) as exc:
            raise AuthenticationFailed('bad token') from exc

    monkeypatch.setattr('users.authentication.user_for_token', fake_user_for_token)
    from studyplatform.asgi import application

    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(application, host='127.0.0.1', port=port, log_level='warning', lifespan='off'))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not srv.started and time.time() < deadline:
        time.sleep(0.05)
    assert srv.started, 'uvicorn did not start'
    yield f'http://127.0.0.1:{port}'
    srv.should_exit = True
    thread.join(timeout=5)


class Player:
    """One browser: a socket that remembers what arrived, and an HTTP client."""

    def __init__(self, base, user):
        self.base, self.user = base, user
        self.sio = socketio.AsyncClient(reconnection=False)
        self.http = httpx.AsyncClient(base_url=base, headers={'Authorization': f'Bearer token-{user.id}',
                                                              'Host': 'localhost'}, timeout=WAIT)
        self.events = []
        for name in ('live:state', 'live:open', 'live:closed'):
            self.sio.on(name, self._keep(name))

    def _keep(self, name):
        async def handler(payload):
            self.events.append((name, payload))
        return handler

    async def connect(self):
        await self.sio.connect(self.base, auth={'token': f'token-{self.user.id}'}, transports=['websocket'],
                               wait_timeout=WAIT)

    async def post(self, path, body=None):
        res = await self.http.post(f'/api/live/rooms/{path}', json=body or {})
        assert res.status_code < 300, (path, res.status_code, res.text)
        return res.json()

    async def until(self, test, what):
        """Wait for a received event that passes `test`."""
        deadline = time.monotonic() + WAIT
        while time.monotonic() < deadline:
            for name, payload in self.events:
                if test(name, payload):
                    return payload
            await asyncio.sleep(0.05)
        raise AssertionError(f'{self.user.email} never received {what}; got {[n for n, _ in self.events]}')

    async def close(self):
        await self.sio.disconnect()
        await self.http.aclose()


def _state(status, index=None):
    return lambda name, p: name == 'live:state' and p['status'] == status and (index is None or p['index'] == index)


def test_two_players_play_a_round_over_the_wire(server, user, other_user, shared_notebook):
    qs = _questions(user, shared_notebook, n=2)
    stranger = get_user_model().objects.create_user(username='supabase:stranger', email='stranger@example.com')

    async def play():
        host, guest, outsider = Player(server, user), Player(server, other_user), Player(server, stranger)
        for p in (host, guest, outsider):
            await p.connect()
        try:
            room = await host.post('', {'notebook': shared_notebook.id, 'question_count': 2, 'seconds': 15})
            rid = room['id']

            # The other member hears that a room opened; the outsider does not.
            opened = await guest.until(lambda n, p: n == 'live:open' and p['id'] == rid, 'live:open')
            assert opened['host']['user_id'] == user.id

            # Watching a room is for members only.
            assert await host.sio.call('live:join', {'room': rid}, timeout=WAIT) == {'ok': True}
            assert await guest.sio.call('live:join', {'room': rid}, timeout=WAIT) == {'ok': True}
            assert await outsider.sio.call('live:join', {'room': rid}, timeout=WAIT) == {'ok': False}

            await guest.post(f'{rid}/join/')
            await host.post(f'{rid}/start/')
            started = await guest.until(_state('question', 0), 'the first question')
            assert 'correct' not in str(started.get('reveal')) and 'you' not in started

            for index in range(2):
                shown = await host.until(_state('question', index), f'question {index}')
                correct = {q.id: q.correct_answer for q in qs}[shown['question']['id']]
                await host.post(f'{rid}/answer/', {'index': index, 'choice': correct})
                await guest.post(f'{rid}/answer/', {'index': index, 'choice': 'b'})
                revealed = await host.until(_state('reveal', index), f'reveal {index}')
                assert revealed['reveal']['correct'] == correct and revealed['reveal']['right'] == [user.id]
                assert revealed['reveal']['counts'] == {'a': 1, 'b': 1, 'c': 0, 'd': 0}

                await guest.post(f'{rid}/next/', {'index': index})
                half = await host.until(lambda n, p, i=index: n == 'live:state' and p['status'] == 'reveal'
                                        and p['index'] == i and p['next_votes'] == 1, f'vote 1/2 on {index}')
                assert half['voters'] == [other_user.id]
                await host.post(f'{rid}/next/', {'index': index})

            finished = await guest.until(_state('finished'), 'the end of the round')
            assert [(r['user_id'], r['score']) for r in finished['results']] == [(user.id, 2), (other_user.id, 0)]
            await guest.until(lambda n, p: n == 'live:closed' and p['id'] == rid, 'live:closed')

            # The outsider saw nothing of the room at all.
            assert not [n for n, p in outsider.events if p.get('id') == rid]
        finally:
            for p in (host, guest, outsider):
                await p.close()

    asyncio.run(play())


def test_a_socket_without_a_valid_token_is_refused(server):
    async def attempt():
        client = socketio.AsyncClient(reconnection=False)
        with pytest.raises(socketio.exceptions.ConnectionError):
            await client.connect(server, auth={'token': 'token-nobody'}, transports=['websocket'], wait_timeout=WAIT)
        await client.disconnect()

    asyncio.run(attempt())
