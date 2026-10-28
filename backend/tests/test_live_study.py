"""Live study: a round of questions a shared notebook answers together.

One question at a time, everyone at once; after each, the group sees the
answer and how it split, and someone moves on. The server's clock decides
what counts as late, and the right answer stays on the server until the
reveal, so nothing in the payload gives it away.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from live.models import LiveSession
from quizzes.models import MockTest, MockTestQuestion, Question, Quiz

pytestmark = pytest.mark.django_db
ROOMS = '/api/live/rooms/'


@pytest.fixture(autouse=True)
def _no_broadcast(monkeypatch):
    sent = []
    monkeypatch.setattr('live.views.broadcast', lambda *a: sent.append(a))
    return sent


def _questions(user, notebook, n=6, kind='multiple_choice'):
    quiz = Quiz.objects.create(user=user, title='Pool', is_published=True)
    quiz.sources.set(notebook.sources.all())
    options = ['True', 'False'] if kind == 'true_false' else ['a', 'b', 'c', 'd']
    return [Question.objects.create(quiz=quiz, question_text=f'Q{i}?', question_type=kind,
                                    options=options, correct_answer=options[0], order=i,
                                    explanation=f'Because {i}.')
            for i in range(n)]


def _open(client, notebook, **extra):
    return client.post(ROOMS, {'notebook': notebook.id, **extra}, format='json')


def _room(client, notebook, **extra):
    return _open(client, notebook, **extra).json()


def _started(client, other_client, notebook, count=5):
    room = _room(client, notebook, question_count=count)
    other_client.post(f'{ROOMS}{room["id"]}/join/')
    return client.post(f'{ROOMS}{room["id"]}/start/').json()


def _answer(c, room, choice, index=None):
    return c.post(f'{ROOMS}{room["id"]}/answer/', {'index': room['index'] if index is None else index,
                                                    'choice': choice}, format='json')


def _age_question(room_id, seconds):
    s = LiveSession.objects.get(pk=room_id)
    s.question_started_at = timezone.now() - timedelta(seconds=seconds)
    s.save(update_fields=['question_started_at'])


# ---- opening and joining -------------------------------------------------------

def test_a_member_opens_a_room_and_is_its_host(client, user, shared_notebook):
    _questions(user, shared_notebook)
    res = _open(client, shared_notebook, question_count=5, seconds=30)

    assert res.status_code == 201
    room = res.json()
    assert room['status'] == 'lobby' and room['total'] == 5 and room['seconds'] == 30
    assert room['host']['user_id'] == user.id
    assert [p['user_id'] for p in room['players']] == [user.id]


def test_opening_again_joins_the_room_that_is_open(client, other_client, user, other_user, shared_notebook):
    _questions(user, shared_notebook)
    first = _room(client, shared_notebook)
    res = _open(other_client, shared_notebook)

    assert res.status_code == 200 and res.json()['id'] == first['id']
    assert {p['user_id'] for p in res.json()['players']} == {user.id, other_user.id}
    assert LiveSession.objects.count() == 1


def test_a_stranger_can_neither_open_nor_join(client, other_client, user, notebook):
    _questions(user, notebook)                      # not shared: other_user is no member
    assert _open(other_client, notebook).status_code in (403, 404)
    room = _room(client, notebook)
    assert other_client.post(f'{ROOMS}{room["id"]}/join/').status_code in (403, 404)
    assert other_client.get(f'{ROOMS}{room["id"]}/').status_code in (403, 404)


def test_a_notebook_without_usable_questions_cannot_open_a_room(client, user, shared_notebook):
    _questions(user, shared_notebook, kind='short_answer')    # typed answers need the AI grader
    res = _open(client, shared_notebook)
    assert res.status_code == 400 and res.json()['no_questions'] is True


def test_the_round_is_no_longer_than_the_pool(client, user, shared_notebook):
    _questions(user, shared_notebook, n=3)
    assert _room(client, shared_notebook, question_count=10)['total'] == 3


def test_true_false_questions_are_used_too(client, user, shared_notebook):
    _questions(user, shared_notebook, n=2, kind='true_false')
    assert _room(client, shared_notebook)['total'] == 2


def test_questions_the_group_owes_come_first(client, user, other_user, shared_notebook):
    qs = _questions(user, shared_notebook, n=12)
    owed = [qs[7], qs[9]]
    test = MockTest.objects.create(user=other_user, notebook=shared_notebook, question_count=2,
                                   duration_minutes=5, completed_at=timezone.now(), score=0)
    for i, q in enumerate(owed):
        MockTestQuestion.objects.create(mock_test=test, question=q, order=i, question_text=q.question_text,
                                        options=q.options, correct_answer='a', user_answer='b',
                                        is_correct=False, answered_at=timezone.now())

    room = _room(client, shared_notebook, question_count=5)

    chosen = LiveSession.objects.get(pk=room['id']).question_ids
    assert set(chosen[:2]) == {q.id for q in owed}


def test_my_open_rooms_are_listed(client, other_client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _room(client, shared_notebook)
    listed = other_client.get(ROOMS).json()['rooms']
    assert [r['id'] for r in listed] == [room['id']]
    assert listed[0]['notebook']['title'] == shared_notebook.title
    assert listed[0]['joined'] is False and client.get(ROOMS).json()['rooms'][0]['joined'] is True


def test_a_room_left_idle_for_hours_closes_itself(client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _room(client, shared_notebook)
    LiveSession.objects.filter(pk=room['id']).update(updated_at=timezone.now() - timedelta(hours=3))

    again = _room(client, shared_notebook)

    assert again['id'] != room['id']
    assert LiveSession.objects.get(pk=room['id']).status == 'finished'


# ---- playing -------------------------------------------------------------------

def test_only_the_host_starts(client, other_client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _room(client, shared_notebook)
    other_client.post(f'{ROOMS}{room["id"]}/join/')
    assert other_client.post(f'{ROOMS}{room["id"]}/start/').status_code == 403
    started = client.post(f'{ROOMS}{room["id"]}/start/').json()
    assert started['status'] == 'question' and started['index'] == 0


def test_the_answer_is_not_in_the_payload_before_the_reveal(client, other_client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _started(client, other_client, shared_notebook)

    assert room['question']['options'] == ['a', 'b', 'c', 'd']
    assert room['reveal'] is None
    assert 'correct_answer' not in str(room) and 'Because' not in str(room)
    assert 0 < room['remaining_ms'] <= 20_000


def test_one_answer_each_and_no_changing_it(client, other_client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _started(client, other_client, shared_notebook)

    assert _answer(client, room, 'b').status_code == 200
    assert _answer(client, room, 'a').status_code == 409
    assert client.get(f'{ROOMS}{room["id"]}/').json()['you']['answer'] == 'b'


def test_a_choice_that_is_not_an_option_is_refused(client, other_client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _started(client, other_client, shared_notebook)
    assert _answer(client, room, 'z').status_code == 400


def test_an_answer_to_another_question_is_refused(client, other_client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _started(client, other_client, shared_notebook)
    assert _answer(client, room, 'a', index=1).status_code == 409


def test_a_late_answer_is_refused(client, other_client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _started(client, other_client, shared_notebook)
    _age_question(room['id'], 20 + 3)
    assert _answer(client, room, 'a').status_code == 409


def test_the_reveal_comes_once_everyone_has_answered(client, other_client, user, other_user, shared_notebook):
    _questions(user, shared_notebook)
    room = _started(client, other_client, shared_notebook)

    first = _answer(client, room, 'a').json()
    assert first['status'] == 'question' and first['answered_count'] == 1
    revealed = _answer(other_client, room, 'b').json()

    assert revealed['status'] == 'reveal'
    reveal = revealed['reveal']
    assert reveal['correct'] == 'a'
    assert reveal['counts'] == {'a': 1, 'b': 1, 'c': 0, 'd': 0}
    assert reveal['right'] == [user.id]
    assert reveal['explanation'] == Question.objects.get(pk=revealed['question']['id']).explanation


def test_no_reveal_before_the_time_is_up_unless_all_answered(client, other_client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _started(client, other_client, shared_notebook)
    _answer(client, room, 'a')

    assert client.post(f'{ROOMS}{room["id"]}/reveal/').json()['status'] == 'question'
    _age_question(room['id'], 21)
    assert other_client.post(f'{ROOMS}{room["id"]}/reveal/').json()['status'] == 'reveal'


def test_next_is_for_the_host_or_anyone_once_the_reveal_has_sat(client, other_client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _started(client, other_client, shared_notebook)
    _answer(client, room, 'a')
    _answer(other_client, room, 'a')

    assert other_client.post(f'{ROOMS}{room["id"]}/next/', {'index': 0}, format='json').status_code == 403
    LiveSession.objects.filter(pk=room['id']).update(revealed_at=timezone.now() - timedelta(seconds=21))
    moved = other_client.post(f'{ROOMS}{room["id"]}/next/', {'index': 0}, format='json').json()
    assert moved['status'] == 'question' and moved['index'] == 1


def test_two_presses_of_next_move_on_once(client, other_client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _started(client, other_client, shared_notebook)
    _answer(client, room, 'a')
    _answer(other_client, room, 'a')

    client.post(f'{ROOMS}{room["id"]}/next/', {'index': 0}, format='json')
    again = client.post(f'{ROOMS}{room["id"]}/next/', {'index': 0}, format='json').json()
    assert again['index'] == 1


def test_the_end_ranks_by_score_then_time_and_lists_my_misses(client, other_client, user, other_user, shared_notebook):
    _questions(user, shared_notebook, n=2)
    room = _started(client, other_client, shared_notebook, count=2)
    for i in range(2):
        _answer(client, room, 'a', index=i)                       # host: both right
        _answer(other_client, room, 'b' if i == 0 else 'a', index=i)
        client.post(f'{ROOMS}{room["id"]}/next/', {'index': i}, format='json')

    end = other_client.get(f'{ROOMS}{room["id"]}/').json()
    assert end['status'] == 'finished'
    assert [(r['user_id'], r['score']) for r in end['results']] == [(user.id, 2), (other_user.id, 1)]
    assert [m['your_answer'] for m in end['you']['missed']] == ['b']
    assert end['you']['missed'][0]['correct'] == 'a'


def test_a_tie_goes_to_the_faster(client, other_client, user, other_user, shared_notebook):
    from live.models import LiveAnswer
    _questions(user, shared_notebook, n=1)
    room = _started(client, other_client, shared_notebook, count=1)
    _answer(client, room, 'a')
    _answer(other_client, room, 'a')
    LiveAnswer.objects.filter(user=user).update(ms=9000)
    LiveAnswer.objects.filter(user=other_user).update(ms=3000)
    client.post(f'{ROOMS}{room["id"]}/next/', {'index': 0}, format='json')

    end = client.get(f'{ROOMS}{room["id"]}/').json()
    assert [r['user_id'] for r in end['results']] == [other_user.id, user.id]


def test_a_miss_in_a_live_round_enters_the_mistake_bank(client, other_client, user, other_user, shared_notebook):
    qs = _questions(user, shared_notebook, n=1)
    room = _started(client, other_client, shared_notebook, count=1)
    _answer(client, room, 'a')
    _answer(other_client, room, 'c')

    bank = other_client.get(f'/api/quizzes/mistakes/?notebook={shared_notebook.id}').json()
    assert [q['id'] for q in bank['questions']] == [qs[0].id]


def test_when_the_host_leaves_the_lobby_someone_else_hosts(client, other_client, user, other_user, shared_notebook):
    _questions(user, shared_notebook)
    room = _room(client, shared_notebook)
    other_client.post(f'{ROOMS}{room["id"]}/join/')

    after = client.post(f'{ROOMS}{room["id"]}/leave/').json()
    assert after['host']['user_id'] == other_user.id
    assert [p['user_id'] for p in after['players']] == [other_user.id]


def test_the_last_one_out_closes_the_room(client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _room(client, shared_notebook)
    assert client.post(f'{ROOMS}{room["id"]}/leave/').json()['status'] == 'finished'


def test_someone_who_left_does_not_hold_up_the_reveal(client, other_client, user, shared_notebook):
    _questions(user, shared_notebook)
    room = _started(client, other_client, shared_notebook)
    other_client.post(f'{ROOMS}{room["id"]}/leave/')
    assert _answer(client, room, 'a').json()['status'] == 'reveal'


def test_every_change_is_broadcast_to_the_room(client, other_client, user, shared_notebook, _no_broadcast):
    _questions(user, shared_notebook)
    room = _started(client, other_client, shared_notebook)
    events = [(a[0], a[1]) for a in _no_broadcast]
    assert (f'live-{room["id"]}', 'live:state') in events
    payloads = [a[2] for a in _no_broadcast if a[1] == 'live:state']
    assert all('you' not in p for p in payloads)


def test_opening_a_room_tells_the_other_members(client, user, other_user, shared_notebook, _no_broadcast):
    _questions(user, shared_notebook)
    _room(client, shared_notebook)
    opened = [a for a in _no_broadcast if a[1] == 'live:open']
    assert [a[0] for a in opened] == [f'user-{other_user.id}']


def test_only_a_member_may_watch_a_room_over_the_socket(client, user, other_user, notebook):
    from live.services.rounds import may_watch
    _questions(user, notebook)
    room = _room(client, notebook)
    assert may_watch(user.id, room['id']) is True
    assert may_watch(other_user.id, room['id']) is False
    assert may_watch(user.id, 999_999) is False
