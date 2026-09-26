"""The Socket.IO server: the notebook chat, delivered as it happens.

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
    notebook_id = (data or {}).get('notebook')
    if not session or not notebook_id:
        return
    room = f'notebook-{notebook_id}'
    if room not in sio.rooms(sid):
        return
    await sio.emit('typing', {'notebook': notebook_id, 'name': session.get('name')},
                   room=room, skip_sid=sid)


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


def emit_to_notebook(notebook_id: int, event: str, payload: dict) -> None:
    """Called from Django's synchronous views."""
    try:
        async_to_sync(sio.emit)(event, payload, room=f'notebook-{notebook_id}')
    except Exception as exc:  # noqa: BLE001 — delivery is best effort
        logger.warning('Socket broadcast failed (%s): %s', event, exc)
