"""Nhắn riêng: chỉ giữa những người có chung ít nhất một sổ tay."""
import pytest

from notebooks.models import DirectMessage, NotebookMember

pytestmark = pytest.mark.django_db


def _send(client, to_user, body='Chào bạn'):
    return client.post(f'/api/notebooks/chat/direct/{to_user.id}/', {'body': body}, format='json')


def _history(client, other):
    return client.get(f'/api/notebooks/chat/direct/{other.id}/')


def test_two_people_in_the_same_notebook_can_message_each_other(client, other_client, user, other_user, shared_notebook):
    res = _send(client, other_user, 'Tối nay học chung nhé')

    assert res.status_code == 201, res.json()
    assert res.json()['body'] == 'Tối nay học chung nhé'
    seen = _history(other_client, user).json()['messages']
    assert [m['body'] for m in seen] == ['Tối nay học chung nhé']
    assert seen[0]['author']['is_you'] is False


def test_a_stranger_cannot_be_messaged(client, other_user, notebook):
    # `notebook` is not shared: the two have nothing in common.
    assert _send(client, other_user).status_code == 403
    assert DirectMessage.objects.count() == 0


def test_a_thread_holds_both_sides_in_order(client, other_client, user, other_user, shared_notebook):
    _send(client, other_user, 'một')
    _send(other_client, user, 'hai')
    _send(client, other_user, 'ba')

    assert [m['body'] for m in _history(client, other_user).json()['messages']] == ['một', 'hai', 'ba']


def test_one_thread_is_invisible_to_a_third_person(client, other_user, user, shared_notebook, django_user_model):
    third = django_user_model.objects.create_user(username='third', first_name='Ba')
    NotebookMember.objects.create(notebook=shared_notebook, user=third, role='member')
    _send(client, other_user, 'chỉ hai đứa mình')

    from rest_framework.test import APIClient
    third_client = APIClient(HTTP_HOST='localhost'); third_client.force_authenticate(third)
    assert _history(third_client, user).json()['messages'] == []


def test_an_empty_message_is_refused(client, other_user, shared_notebook):
    assert _send(client, other_user, '   ').status_code == 400


def test_you_cannot_message_yourself(client, user, shared_notebook):
    assert _send(client, user).status_code == 400


# ---- what the chat launcher lists -------------------------------------------------

def _overview(client):
    return client.get('/api/notebooks/chat/overview/').json()


def test_the_overview_lists_the_notebooks_and_the_people_you_share_them_with(client, user, other_user, shared_notebook):
    body = _overview(client)

    assert [g['notebook'] for g in body['groups']] == [shared_notebook.id]
    assert body['groups'][0]['title'] == shared_notebook.title
    assert [p['user_id'] for p in body['people']] == [other_user.id]
    assert body['people'][0]['name']


def test_the_overview_carries_the_last_line_of_each_conversation(client, other_client, user, other_user, shared_notebook):
    client.post(f'/api/notebooks/notebooks/{shared_notebook.id}/messages/', {'body': 'tin nhóm'}, format='json')
    _send(other_client, user, 'tin riêng')

    body = _overview(client)

    assert body['groups'][0]['last']['body'] == 'tin nhóm'
    assert body['people'][0]['last']['body'] == 'tin riêng'
    assert body['people'][0]['last']['is_you'] is False


def test_a_notebook_you_are_alone_in_lists_no_people(client, notebook):
    body = _overview(client)
    assert [g['notebook'] for g in body['groups']] == [notebook.id]
    assert body['people'] == []
