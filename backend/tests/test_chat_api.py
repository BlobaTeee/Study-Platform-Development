"""The group chat inside a shared notebook: history and sending."""
import pytest

from notebooks.models import Notebook, NotebookMessage

pytestmark = pytest.mark.django_db


def _send(client, notebook, body='Chào cả nhóm'):
    return client.post(f'/api/notebooks/notebooks/{notebook.id}/messages/', {'body': body}, format='json')


def _history(client, notebook, **params):
    q = '&'.join(f'{k}={v}' for k, v in params.items())
    return client.get(f'/api/notebooks/notebooks/{notebook.id}/messages/' + (f'?{q}' if q else ''))


def test_a_member_sends_a_message_and_everyone_in_the_notebook_reads_it(client, other_client, user, shared_notebook):
    res = _send(client, shared_notebook, 'Tối nay ôn chương 3 nhé')

    assert res.status_code == 201, res.json()
    assert res.json()['body'] == 'Tối nay ôn chương 3 nhé'
    assert res.json()['author']['is_you'] is True
    seen = _history(other_client, shared_notebook).json()['messages']
    assert [m['body'] for m in seen] == ['Tối nay ôn chương 3 nhé']
    assert seen[0]['author']['name'] and seen[0]['author']['is_you'] is False


def test_history_reads_oldest_first_and_pages_from_the_end(client, user, shared_notebook):
    for i in range(5):
        NotebookMessage.objects.create(notebook=shared_notebook, user=user, body=f'tin {i}')

    page = _history(client, shared_notebook, limit=2).json()

    assert [m['body'] for m in page['messages']] == ['tin 3', 'tin 4']
    older = _history(client, shared_notebook, limit=2, before=page['messages'][0]['id']).json()
    assert [m['body'] for m in older['messages']] == ['tin 1', 'tin 2']


def test_an_empty_message_is_refused(client, shared_notebook):
    assert _send(client, shared_notebook, '   ').status_code == 400
    assert NotebookMessage.objects.count() == 0


def test_a_very_long_message_is_refused_rather_than_truncated(client, shared_notebook):
    assert _send(client, shared_notebook, 'x' * 2001).status_code == 400


def test_someone_outside_the_notebook_can_neither_read_nor_send(client, other_user):
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    assert _history(client, theirs).status_code == 404
    assert _send(client, theirs).status_code == 404


def test_a_member_deletes_their_own_message_only(other_client, user, other_user, shared_notebook):
    # `other_user` is a plain member here; `user` owns the notebook.
    mine = NotebookMessage.objects.create(notebook=shared_notebook, user=other_user, body='của tôi')
    owners = NotebookMessage.objects.create(notebook=shared_notebook, user=user, body='của chủ sổ')

    assert other_client.delete(f'/api/notebooks/messages/{mine.id}/').status_code == 204
    assert other_client.delete(f'/api/notebooks/messages/{owners.id}/').status_code == 403
    assert NotebookMessage.objects.filter(id=owners.id).exists()


def test_the_notebook_owner_can_delete_any_message(client, other_user, shared_notebook):
    theirs = NotebookMessage.objects.create(notebook=shared_notebook, user=other_user, body='của bạn')
    assert client.delete(f'/api/notebooks/messages/{theirs.id}/').status_code == 204
