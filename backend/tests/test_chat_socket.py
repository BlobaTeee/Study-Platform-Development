"""Lớp realtime, kiểm ở chỗ logic của nó nằm: ai vào được room nào, và một
tin nhắn trông thế nào khi lên dây."""
import pytest

from notebooks.models import ChatGroup, ChatGroupMember, GroupMessage
from notebooks.services.chat import (
    MAX_BODY_CHARS, create_group, message_payload, post_message, room_for, rooms_for_user,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def group(user, other_user, shared_notebook):
    return create_group(user, 'Nhóm ôn thi', [other_user.id])


def test_a_room_name_is_derived_from_the_group(group):
    assert room_for(group.id) == f'group-{group.id}'


def test_every_member_gets_the_groups_room(user, other_user, group):
    assert rooms_for_user(user) == [room_for(group.id)]
    assert rooms_for_user(other_user) == [room_for(group.id)]


def test_someone_in_no_group_gets_no_rooms(other_user, notebook):
    assert rooms_for_user(other_user) == []


def test_posting_returns_the_payload_that_goes_on_the_wire(user, group):
    message = post_message(group, user, '  Xin chào  ')

    payload = message_payload(message)
    assert payload['body'] == 'Xin chào'                  # trimmed
    assert payload['group'] == group.id
    assert payload['author']['user_id'] == user.id
    assert payload['author']['name']
    assert 'created_at' in payload


def test_an_empty_or_oversized_body_is_refused(user, group):
    with pytest.raises(ValueError):
        post_message(group, user, '   ')
    with pytest.raises(ValueError):
        post_message(group, user, 'x' * (MAX_BODY_CHARS + 1))
    assert GroupMessage.objects.count() == 0


def test_an_outsider_cannot_post(other_user, django_user_model):
    stranger = django_user_model.objects.create_user(username='stranger')
    group = ChatGroup.objects.create(name='Riêng', created_by=other_user)
    ChatGroupMember.objects.create(group=group, user=other_user)
    with pytest.raises(PermissionError):
        post_message(group, stranger, 'lén vào')
