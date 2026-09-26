"""The realtime layer, tested where its logic lives: who may connect, who
may join a room, and what a delivered message looks like."""
import pytest

from notebooks.models import NotebookMessage
from notebooks.services.chat import (
    MAX_BODY_CHARS, message_payload, post_message, room_for, rooms_for_user,
)

pytestmark = pytest.mark.django_db


def test_a_room_name_is_derived_from_the_notebook(notebook):
    assert room_for(notebook.id) == f'notebook-{notebook.id}'


def test_a_user_gets_a_room_for_every_notebook_they_are_in(user, other_user, shared_notebook):
    assert rooms_for_user(user) == [room_for(shared_notebook.id)]
    assert rooms_for_user(other_user) == [room_for(shared_notebook.id)]


def test_a_stranger_gets_no_rooms(other_user, notebook):
    assert rooms_for_user(other_user) == []


def test_posting_returns_the_payload_that_goes_on_the_wire(user, shared_notebook):
    message = post_message(shared_notebook, user, '  Xin chào  ')

    payload = message_payload(message)
    assert payload['body'] == 'Xin chào'                  # trimmed
    assert payload['notebook'] == shared_notebook.id
    assert payload['author']['user_id'] == user.id
    assert payload['author']['name']
    assert 'created_at' in payload


def test_an_empty_or_oversized_body_is_refused(user, shared_notebook):
    with pytest.raises(ValueError):
        post_message(shared_notebook, user, '   ')
    with pytest.raises(ValueError):
        post_message(shared_notebook, user, 'x' * (MAX_BODY_CHARS + 1))
    assert NotebookMessage.objects.count() == 0


def test_a_non_member_cannot_post(other_user, notebook):
    with pytest.raises(PermissionError):
        post_message(notebook, other_user, 'lén vào')
