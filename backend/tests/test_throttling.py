"""Generation is metered per user; everything else is not, or barely."""
import pytest

from studyplatform.throttling import GenerationRateThrottle

# The allowance as deployed; a local .env may lift it for a demo.
LIMIT = 30


@pytest.fixture(autouse=True)
def deployed_rate(monkeypatch):
    monkeypatch.setattr(GenerationRateThrottle, 'rate', f'{LIMIT}/hour', raising=False)

pytestmark = pytest.mark.django_db


def _generate(client, notebook):
    # An empty selection is refused by the view body (400), which is what
    # makes this a cheap way to spend the allowance: the throttle runs before
    # the body, so every one of these counts, and none touches a provider.
    return client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_flashcards/',
                       {'source_ids': []}, format='json')


def test_one_over_the_hourly_allowance_is_refused(client, notebook):
    codes = [_generate(client, notebook).status_code for _ in range(LIMIT + 1)]

    assert codes[:LIMIT] == [400] * LIMIT
    assert codes[LIMIT] == 429


def test_flashcard_and_quiz_generation_share_one_allowance(client, notebook):
    for _ in range(LIMIT):
        _generate(client, notebook)

    res = client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_quiz/',
                      {'source_ids': []}, format='json')

    assert res.status_code == 429


def test_starting_a_mock_test_spends_the_same_allowance(client, notebook):
    for _ in range(LIMIT):
        _generate(client, notebook)

    res = client.post('/api/quizzes/mock-tests/', {'notebook': notebook.id}, format='json')

    assert res.status_code == 429


def test_reads_are_not_slowed_by_a_generation_spree(client, notebook):
    for _ in range(LIMIT + 1):
        _generate(client, notebook)

    assert client.get('/api/notebooks/notebooks/').status_code == 200


def test_the_allowance_is_per_user(client, other_user, notebook):
    from rest_framework.test import APIClient
    for _ in range(LIMIT + 1):
        _generate(client, notebook)
    theirs = APIClient(HTTP_HOST='localhost')
    theirs.force_authenticate(other_user)

    # Their first call: not throttled (404, since the notebook isn't theirs —
    # which is a body response, so the throttle let it through).
    assert _generate(theirs, notebook).status_code == 404


def test_the_refusal_says_when_in_minutes(client, notebook):
    for _ in range(LIMIT):
        _generate(client, notebook)
    res = _generate(client, notebook)
    assert res.status_code == 429
    assert 'min' in res.json()['detail'] and 'seconds' not in res.json()['detail']


def test_a_request_the_ai_could_not_serve_is_given_back(client, notebook, monkeypatch):
    """Retrying through an overload does not use up the allowance."""
    from exercises.services import problems
    from exercises.services.common import PracticeUnavailable

    def overloaded(*a, **k):
        raise PracticeUnavailable('busy')
    monkeypatch.setattr(problems, 'own_set', overloaded)
    for _ in range(LIMIT + 3):
        res = client.post('/api/exercises/own-set/', {'texts': ['Câu 1. Tính diện tích hình vuông có cạnh bằng 3 cm.']}, format='json')
        assert res.status_code == 503
    assert _generate(client, notebook).status_code == 400       # still allowed


def test_off_lifts_the_allowance(client, notebook, monkeypatch):
    from studyplatform.settings import _rate_or_none
    assert _rate_or_none('off') is None and _rate_or_none('30/hour') == '30/hour'
    monkeypatch.setattr(GenerationRateThrottle, 'rate', None, raising=False)
    monkeypatch.setitem(GenerationRateThrottle.THROTTLE_RATES, 'generate', None)
    codes = {_generate(client, notebook).status_code for _ in range(LIMIT + 5)}
    assert codes == {400}
