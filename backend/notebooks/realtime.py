"""The Socket.IO server: the chat and live rounds, delivered as they happen.

Runs inside the same ASGI process as Django (see studyplatform/asgi.py), so
it shares the database, the Supabase token check and the membership rules
rather than re-implementing any of them. Sending a message is still a REST
call — this layer's job is delivery, and a socket that drops does not cost
anyone their message.
"""
import logging

import socketio
from asgiref.sync import async_to_sync, sync_to_async

logger = logging.getLogger(__name__)

# `async_mode='asgi'` keeps one server object for the whole process; with
# several workers a message queue (Redis) would go here so a broadcast
# reaches clients attached to the other workers.
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', logger=False)


@sio.event
async def connect(sid, environ, auth):
    """Admit a client that presents a valid Supabase token, and put it in
    the rooms of every notebook it belongs to."""
    token = (auth or {}).get('token') if isinstance(auth, dict) else None
    user = await _user_from_token(token)
    if user is None:
        # Refusing here closes the socket with an error the client can show.
        raise socketio.exceptions.ConnectionRefusedError('sign in first')
    rooms = await _rooms_for(user)
    # Plus this person's own room, where their private messages arrive.
    rooms = [f'user-{user.id}', *rooms]
    for room in rooms:
        await sio.enter_room(sid, room)
    await sio.save_session(sid, {'user_id': user.id, 'name': user.first_name})
    await sio.emit('ready', {'rooms': rooms}, to=sid)


@sio.event
async def disconnect(sid):
    pass          # rooms are dropped with the socket


@sio.event
async def typing(sid, data):
    """Tell the rest of the room someone is writing. Not stored: it is only
    true for the second it is said."""
    session = await sio.get_session(sid)
    notebook_id = (data or {}).get('group')
    if not session or not notebook_id:
        return
    room = f'group-{notebook_id}'
    if room not in sio.rooms(sid):
        return
    await sio.emit('typing', {'group': notebook_id, 'name': session.get('name')},
                   room=room, skip_sid=sid)


@sio.on('live:join')
async def live_join(sid, data):
    """Watch a live round. Only a member of its notebook is let in; the
    round's state itself still comes from REST, this only delivers changes."""
    session = await sio.get_session(sid)
    room_id = (data or {}).get('room')
    if not session or not room_id or not await _may_watch(session['user_id'], room_id):
        return {'ok': False}
    await sio.enter_room(sid, f'live-{room_id}')
    return {'ok': True}


@sio.on('live:leave')
async def live_leave(sid, data):
    room_id = (data or {}).get('room')
    if room_id:
        await sio.leave_room(sid, f'live-{room_id}')


@sync_to_async
def _may_watch(user_id, room_id):
    from live.services.rounds import may_watch
    return may_watch(user_id, room_id)


@sync_to_async
def _user_from_token(token):
    if not token:
        return None
    from users.authentication import user_for_token
    try:
        return user_for_token(token)
    except Exception as exc:  # noqa: BLE001 — an unverifiable token is just a refusal
        logger.info('Socket auth refused: %s', exc)
        return None


@sync_to_async
def _rooms_for(user):
    from .services.chat import rooms_for_user
    return rooms_for_user(user)


def emit_to_room(room: str, event: str, payload: dict) -> None:
    """Called from Django's synchronous views. Delivery is best effort: the
    message is already stored, and a refresh shows it either way."""
    try:
        async_to_sync(sio.emit)(event, payload, room=room)
    except Exception as exc:  # noqa: BLE001
        logger.warning('Socket broadcast failed (%s): %s', event, exc)

