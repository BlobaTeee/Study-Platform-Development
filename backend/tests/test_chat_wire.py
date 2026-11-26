"""Group chat over the real wire (2026-11-26).

The user found a group chat only updated after a reload: a socket was put in
its groups' rooms once, when it connected, so a group made or joined after
that never reached it. Now the server moves members' open sockets in (and a
leaver's out), and the page can ask to join a group it shows.
"""
import asyncio

import pytest
from django.contrib.auth import get_user_model

from tests.test_live_socket import WAIT, Player, server  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db(transaction=True)


class Chatter(Player):
    def __init__(self, base, user):
        super().__init__(base, user)
        for name in ('message:new', 'message:deleted'):
            self.sio.on(name, self._keep(name))

    async def api(self, method, path, body=None):
        res = await self.http.request(method, f'/api/notebooks/chat/{path}', json=body)
        assert res.status_code < 300, (path, res.status_code, res.text)
        return res.json() if res.content else None

    def heard(self, group, body):
        return any(n == 'message:new' and p['group'] == group and p['body'] == body for n, p in self.events)


def test_a_group_made_after_connecting_is_live_for_both(server, user, other_user, shared_notebook):  # noqa: F811
    async def run():
        me, friend = Chatter(server, user), Chatter(server, other_user)
        await me.connect()
        await friend.connect()
        try:
            group = (await me.api('POST', 'groups/', {'name': 'Ôn thi', 'members': [other_user.id]}))['id']
            await me.api('POST', f'groups/{group}/messages/', {'body': 'chào'})
            await friend.until(lambda n, p: n == 'message:new' and p['body'] == 'chào', 'the first message')
            await me.until(lambda n, p: n == 'message:new' and p['body'] == 'chào', 'its own message')

            # Leaving stops the messages at once, not at the next reconnect.
            await friend.api('DELETE', f'groups/{group}/members/{other_user.id}/')
            await me.api('POST', f'groups/{group}/messages/', {'body': 'còn ai không'})
            await me.until(lambda n, p: n == 'message:new' and p['body'] == 'còn ai không', 'the second')
            await asyncio.sleep(0.3)
            assert not friend.heard(group, 'còn ai không')

            # Added back: live again without reconnecting.
            await me.api('POST', f'groups/{group}/members/', {'user_id': other_user.id})
            await me.api('POST', f'groups/{group}/messages/', {'body': 'về rồi'})
            await friend.until(lambda n, p: n == 'message:new' and p['body'] == 'về rồi', 'the third')
        finally:
            await me.close()
            await friend.close()

    asyncio.run(run())


def test_only_a_member_can_ask_to_join_a_group(server, user, other_user, shared_notebook):  # noqa: F811
    stranger = get_user_model().objects.create_user(username='supabase:stranger', email='stranger@example.com')

    async def run():
        me, outsider = Chatter(server, user), Chatter(server, stranger)
        await me.connect()
        await outsider.connect()
        try:
            group = (await me.api('POST', 'groups/', {'name': 'Riêng', 'members': [other_user.id]}))['id']
            assert await me.sio.call('group:join', {'group': group}, timeout=WAIT) == {'ok': True}
            assert await outsider.sio.call('group:join', {'group': group}, timeout=WAIT) == {'ok': False}
            assert await outsider.sio.call('group:join', {'group': 'x'}, timeout=WAIT) == {'ok': False}
            await me.api('POST', f'groups/{group}/messages/', {'body': 'bí mật'})
            await me.until(lambda n, p: n == 'message:new' and p['body'] == 'bí mật', 'its message')
            await asyncio.sleep(0.3)
            assert not outsider.heard(group, 'bí mật')
        finally:
            await me.close()
            await outsider.close()

    asyncio.run(run())
