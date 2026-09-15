"""Generation is metered per user; everything else is not, or barely."""
import pytest

pytestmark = pytest.mark.django_db


def _generate(client, notebook):
    # An empty selection is refused by the view body (400), which is what
    # makes this a cheap way to spend the allowance: the throttle runs before
    # the body, so every one of these counts, and none touches a provider.
    return client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_flashcards/',
                       {'source_ids': []}, format='json')


def test_the_eleventh_generation_in_an_hour_is_refused(client, notebook):
    codes = [_generate(client, notebook).status_code for _ in range(11)]

    assert codes[:10] == [400] * 10
    assert codes[10] == 429


def test_flashcard_and_quiz_generation_share_one_allowance(client, notebook):
    for _ in range(10):
        _generate(client, notebook)

    res = client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_quiz/',
                      {'source_ids': []}, format='json')

    assert res.status_code == 429


def test_starting_a_mock_test_spends_the_same_allowance(client, notebook):
    for _ in range(10):
        _generate(client, notebook)

    res = client.post('/api/quizzes/mock-tests/', {'notebook': notebook.id}, format='json')

    assert res.status_code == 429


def test_reads_are_not_slowed_by_a_generation_spree(client, notebook):
    for _ in range(11):
        _generate(client, notebook)

    assert client.get('/api/notebooks/notebooks/').status_code == 200


def test_the_allowance_is_per_user(client, other_user, notebook):
    from rest_framework.test import APIClient
    for _ in range(11):
        _generate(client, notebook)
    theirs = APIClient(HTTP_HOST='localhost')
    theirs.force_authenticate(other_user)

    # Their first call: not throttled (404, since the notebook isn't theirs —
    # which is a body response, so the throttle let it through).
    assert _generate(theirs, notebook).status_code == 404
