"""Inviting someone to a notebook, and who is in it."""
import pytest
from django.core import mail

from notebooks.models import NotebookInvite, NotebookMember

pytestmark = pytest.mark.django_db


def _invite(client, notebook, email='ban@truong.edu.vn'):
    return client.post(f'/api/notebooks/notebooks/{notebook.id}/invite/', {'email': email}, format='json')


# ---- creating an invitation ---------------------------------------------------------

def test_the_owner_invites_by_email_and_gets_a_link_to_share(client, notebook, settings):
    settings.FRONTEND_URL = 'http://localhost:3000'

    res = _invite(client, notebook)

    assert res.status_code == 201, res.json()
    invite = NotebookInvite.objects.get(notebook=notebook)
    assert res.json()['url'] == f'http://localhost:3000/join/{invite.token}'
    assert len(invite.token) >= 32
    assert res.json()['email'] == 'ban@truong.edu.vn'


def test_the_invitation_is_emailed_when_mail_is_configured(client, notebook, settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    mail.outbox.clear()

    _invite(client, notebook)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ['ban@truong.edu.vn']
    assert notebook.title in mail.outbox[0].subject or notebook.title in mail.outbox[0].body


def test_a_member_cannot_invite(other_client, shared_notebook):
    assert _invite(other_client, shared_notebook).status_code == 403


def test_a_second_invitation_to_the_same_address_reuses_the_link(client, notebook):
    first = _invite(client, notebook).json()
    second = _invite(client, notebook).json()
    assert first['url'] == second['url']
    assert NotebookInvite.objects.filter(notebook=notebook).count() == 1


# ---- accepting ----------------------------------------------------------------------

def test_accepting_puts_you_in_the_notebook(client, other_client, other_user, notebook):
    token = _invite(client, notebook).json()['token']

    res = other_client.post('/api/notebooks/invites/accept/', {'token': token}, format='json')

    assert res.status_code == 200
    assert res.json()['notebook']['id'] == notebook.id
    assert NotebookMember.objects.filter(notebook=notebook, user=other_user, role='member').exists()
    invite = NotebookInvite.objects.get(token=token)
    assert invite.accepted_at is not None and invite.accepted_by == other_user


def test_a_used_link_cannot_be_used_again(client, other_client, notebook, user):
    token = _invite(client, notebook).json()['token']
    other_client.post('/api/notebooks/invites/accept/', {'token': token}, format='json')

    res = client.post('/api/notebooks/invites/accept/', {'token': token}, format='json')

    assert res.status_code == 400


def test_an_unknown_token_is_refused(other_client):
    assert other_client.post('/api/notebooks/invites/accept/',
                             {'token': 'nope'}, format='json').status_code == 404


def test_accepting_twice_by_the_same_person_is_harmless(client, other_client, other_user, notebook):
    token = _invite(client, notebook).json()['token']
    other_client.post('/api/notebooks/invites/accept/', {'token': token}, format='json')
    # A second membership row would be a unique-constraint error, not a 200.
    assert NotebookMember.objects.filter(notebook=notebook, user=other_user).count() == 1


# ---- who is in it -------------------------------------------------------------------

def test_the_member_list_shows_each_persons_record_in_this_notebook(client, user, other_user, shared_notebook):
    from flashcards.models import Flashcard
    from study_sessions.models import CardReview
    card = Flashcard.objects.create(user=user, notebook=shared_notebook, question='q', answer='a')
    card.sources.set(shared_notebook.sources.all())
    CardReview.record(user, card, 'easy')

    body = client.get(f'/api/notebooks/notebooks/{shared_notebook.id}/members/').json()

    assert [m['role'] for m in body['members']] == ['owner', 'member']
    me = body['members'][0]
    assert me['is_you'] is True and me['reviews'] == 1
    assert body['members'][1]['name'] and body['members'][1]['reviews'] == 0


def test_a_member_can_see_who_else_is_in(other_client, shared_notebook):
    assert other_client.get(f'/api/notebooks/notebooks/{shared_notebook.id}/members/').status_code == 200


# ---- leaving and removing -----------------------------------------------------------

def test_a_member_leaves_on_their_own(other_client, other_user, shared_notebook):
    res = other_client.delete(f'/api/notebooks/notebooks/{shared_notebook.id}/members/{other_user.id}/')
    assert res.status_code == 204
    assert not NotebookMember.objects.filter(notebook=shared_notebook, user=other_user).exists()
    assert other_client.get(f'/api/notebooks/notebooks/{shared_notebook.id}/').status_code == 404


def test_the_owner_removes_a_member(client, other_user, shared_notebook):
    assert client.delete(f'/api/notebooks/notebooks/{shared_notebook.id}/members/{other_user.id}/').status_code == 204


def test_a_member_cannot_remove_anyone_else(other_client, user, shared_notebook):
    assert other_client.delete(f'/api/notebooks/notebooks/{shared_notebook.id}/members/{user.id}/').status_code == 403


def test_the_owner_cannot_leave_their_own_notebook(client, user, shared_notebook):
    res = client.delete(f'/api/notebooks/notebooks/{shared_notebook.id}/members/{user.id}/')
    assert res.status_code == 400
    assert NotebookMember.objects.filter(notebook=shared_notebook, user=user, role='owner').exists()
