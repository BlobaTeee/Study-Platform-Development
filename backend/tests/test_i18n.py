"""The API answers in the language the browser is showing."""
import pytest
from rest_framework.test import APIClient

from quizzes.models import Quiz, QuizAttempt

pytestmark = pytest.mark.django_db


def _client(user, lang):
    c = APIClient(HTTP_HOST='localhost', HTTP_ACCEPT_LANGUAGE=lang)
    c.force_authenticate(user)
    return c


def _blank_typed_answer(client, user):
    quiz = Quiz.objects.create(user=user, title='q')
    attempt = QuizAttempt.objects.create(quiz=quiz, user=user)
    return client.post(f'/api/quizzes/attempts/{attempt.id}/grade_typed_answer/',
                       {'question_id': 1, 'answer': '   '}, format='json')


def test_a_refused_request_explains_itself_in_vietnamese(user):
    res = _blank_typed_answer(_client(user, 'vi'), user)
    assert res.status_code == 400
    assert res.json()['detail'] == 'Hãy gõ câu trả lời trước.'


def test_the_same_request_in_english(user):
    res = _blank_typed_answer(_client(user, 'en'), user)
    assert res.json()['detail'] == 'Type an answer first.'


def test_no_header_means_english(client, user):
    res = _blank_typed_answer(client, user)
    assert res.json()['detail'] == 'Type an answer first.'


def test_profile_language_accepts_only_the_supported_ones(client, user):
    ok = client.put('/api/users/profiles/update_profile/', {'preferred_language': 'vi'}, format='json')
    assert ok.status_code == 200 and ok.json()['preferred_language'] == 'vi'
    bad = client.put('/api/users/profiles/update_profile/', {'preferred_language': 'fr'}, format='json')
    assert bad.status_code == 400 and 'preferred_language' in bad.json()


def test_no_translation_is_left_fuzzy():
    # makemessages guesses a translation for a new msgid that resembles an
    # old one and marks it fuzzy; compilemessages then skips it, so the
    # message silently ships in English — or, worse, the guess is wrong and
    # gets copied as if it were right. The header entry is fuzzy by design.
    from pathlib import Path
    po = Path(__file__).resolve().parents[1] / 'locale' / 'vi' / 'LC_MESSAGES' / 'django.po'
    body = po.read_text().split('msgid ""', 1)[1]          # everything after the header
    assert '#, fuzzy' not in body, 'run makemessages, fix the fuzzy entries by hand, remove the flag'
