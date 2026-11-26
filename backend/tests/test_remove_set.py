"""Taking a whole set out of practice at once (2026-11-26): the user found
removing a paper's problems one by one tiring."""
import pytest

from exercises.models import Exercise

pytestmark = pytest.mark.django_db


def _problems(user, n, key='k' * 32):
    return [Exercise.objects.create(user=user, notebook=None, origin='own', set_key=key, set_title='Đề',
                                    prompt=f'Câu {i}', reference={'kind': 'written'}) for i in range(n)]


def test_a_whole_set_goes_in_one_request(client, user):
    keep = _problems(user, 1, key='z' * 32)
    gone = _problems(user, 3)
    res = client.post('/api/exercises/remove/', {'ids': [e.id for e in gone]}, format='json')
    assert res.status_code == 200 and res.json()['removed'] >= 3
    assert list(Exercise.objects.values_list('id', flat=True)) == [keep[0].id]


def test_someone_elses_problems_are_left_alone(client, other_user):
    theirs = _problems(other_user, 2)
    client.post('/api/exercises/remove/', {'ids': [e.id for e in theirs]}, format='json')
    assert Exercise.objects.count() == 2


@pytest.mark.parametrize('body', [{}, {'ids': []}, {'ids': 'all'}, {'ids': ['1']}])
def test_a_bad_list_is_refused(client, user, body):
    _problems(user, 1)
    assert client.post('/api/exercises/remove/', body, format='json').status_code == 400
    assert Exercise.objects.count() == 1


def test_a_set_can_no_longer_be_sat_as_a_paper(client, user):
    _problems(user, 2)
    assert client.post(f"/api/exercises/sets/{'k' * 32}/sit/").status_code in (404, 405)
