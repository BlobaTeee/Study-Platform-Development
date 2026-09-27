"""Nhóm chat: một nhóm là một nhóm, không phải một sổ tay."""
import pytest

from notebooks.models import ChatGroup, ChatGroupMember, GroupMessage

pytestmark = pytest.mark.django_db


def _create(client, name='Nhóm ôn thi', members=()):
    return client.post('/api/notebooks/chat/groups/', {'name': name, 'members': list(members)}, format='json')


def _send(client, group, body='Chào nhóm'):
    return client.post(f'/api/notebooks/chat/groups/{group.id}/messages/', {'body': body}, format='json')


def test_a_group_is_created_with_its_maker_inside(client, user, other_user, shared_notebook):
    res = _create(client, 'Nhóm ôn thi', [other_user.id])

    assert res.status_code == 201, res.json()
    group = ChatGroup.objects.get(id=res.json()['id'])
    assert group.name == 'Nhóm ôn thi'
    assert set(ChatGroupMember.objects.filter(group=group).values_list('user_id', flat=True)) == {user.id, other_user.id}


def test_only_people_you_share_a_notebook_with_can_be_added(client, other_user, notebook):
    # `notebook` is private, so the two have nothing in common.
    res = _create(client, 'Nhóm lạ', [other_user.id])
    assert res.status_code == 400
    assert ChatGroup.objects.count() == 0


def test_a_group_needs_a_name(client, other_user, shared_notebook):
    assert _create(client, '   ', [other_user.id]).status_code == 400


def test_members_send_and_read_the_thread(client, other_client, user, other_user, shared_notebook):
    group = ChatGroup.objects.get(id=_create(client, members=[other_user.id]).json()['id'])

    assert _send(client, group, 'Tối nay 8h nhé').status_code == 201
    seen = other_client.get(f'/api/notebooks/chat/groups/{group.id}/messages/').json()['messages']
    assert [m['body'] for m in seen] == ['Tối nay 8h nhé']
    assert seen[0]['author']['is_you'] is False


def test_an_outsider_can_neither_read_nor_send(client, other_client, other_user, shared_notebook):
    group = ChatGroup.objects.create(name='Riêng', created_by=other_user)
    ChatGroupMember.objects.create(group=group, user=other_user)

    assert client.get(f'/api/notebooks/chat/groups/{group.id}/messages/').status_code == 404
    assert _send(client, group).status_code == 404


def test_the_overview_lists_groups_not_notebooks(client, user, other_user, shared_notebook):
    group = ChatGroup.objects.get(id=_create(client, 'Nhóm ôn thi', [other_user.id]).json()['id'])
    _send(client, group, 'câu cuối')

    body = client.get('/api/notebooks/chat/overview/').json()

    assert [g['id'] for g in body['groups']] == [group.id]
    assert body['groups'][0]['name'] == 'Nhóm ôn thi'
    assert body['groups'][0]['members'] == 2
    assert body['groups'][0]['last']['body'] == 'câu cuối'
    # The people list is still whoever you share study material with.
    assert [p['user_id'] for p in body['people']] == [other_user.id]


def test_someone_can_be_added_to_an_existing_group(client, user, other_user, shared_notebook, django_user_model):
    from notebooks.models import NotebookMember
    third = django_user_model.objects.create_user(username='third', first_name='Ba')
    NotebookMember.objects.create(notebook=shared_notebook, user=third, role='member')
    group = ChatGroup.objects.get(id=_create(client, members=[other_user.id]).json()['id'])

    res = client.post(f'/api/notebooks/chat/groups/{group.id}/members/', {'user_id': third.id}, format='json')

    assert res.status_code == 201, res.json()
    assert ChatGroupMember.objects.filter(group=group, user=third).exists()


def test_a_member_leaves_and_stops_seeing_the_group(client, other_client, other_user, shared_notebook):
    group = ChatGroup.objects.get(id=_create(client, members=[other_user.id]).json()['id'])

    res = other_client.delete(f'/api/notebooks/chat/groups/{group.id}/members/{other_user.id}/')

    assert res.status_code == 204
    assert other_client.get(f'/api/notebooks/chat/groups/{group.id}/messages/').status_code == 404


def test_a_message_is_deleted_by_its_author(client, other_client, user, other_user, shared_notebook):
    group = ChatGroup.objects.get(id=_create(client, members=[other_user.id]).json()['id'])
    mine = GroupMessage.objects.create(group=group, user=user, body='của tôi')

    assert other_client.delete(f'/api/notebooks/messages/{mine.id}/').status_code == 403
    assert client.delete(f'/api/notebooks/messages/{mine.id}/').status_code == 204
