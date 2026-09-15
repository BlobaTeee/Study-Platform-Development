"""Per-notebook mastery, read through the relation."""
import pytest

from flashcards.models import Flashcard
from notebooks.models import Notebook
from quizzes.models import Answer, Question, Quiz, QuizAttempt
from study_sessions.models import CardReview

pytestmark = pytest.mark.django_db

URL = '/api/analytics/sessions/recommendations/'


def _card(user, notebook, sources, grades=()):
    card = Flashcard.objects.create(user=user, notebook=notebook, question='q', answer='a')
    card.sources.set(sources)
    for result in grades:
        CardReview.objects.create(user=user, flashcard=card, result=result)
    return card


def _answered_question(user, sources, correct):
    quiz = Quiz.objects.create(user=user, title='Q')
    quiz.sources.set(sources)
    q = Question.objects.create(quiz=quiz, question_text='?', question_type='multiple_choice',
                                options=['a', 'b'], correct_answer='a', order=0)
    attempt = QuizAttempt.objects.create(quiz=quiz, user=user)
    Answer.objects.create(quiz_attempt=attempt, question=q,
                          user_answer='a' if correct else 'b', is_correct=correct)
    return q


def _by_title(res):
    return {n['title']: n for n in res.json()['weak_notebooks']}


def test_a_card_from_two_sources_in_one_notebook_counts_once(client, user, notebook):
    _card(user, notebook, notebook.sources.all(), grades=['good', 'hard'])

    row = _by_title(client.get(URL))['Biology']

    assert row['cards'] == 1
    assert row['reviews'] == 2
    assert row['accuracy'] == 50.0


def test_flashcard_and_quiz_evidence_pool_into_one_score(client, user, notebook):
    cells = notebook.sources.first()
    _card(user, notebook, [cells], grades=['good'])          # 1/1
    _answered_question(user, [cells], correct=False)         # 0/1

    row = _by_title(client.get(URL))['Biology']

    assert row['cards'] == 1 and row['questions'] == 1
    assert row['reviews'] == 2
    assert row['accuracy'] == 50.0


def test_a_notebook_nobody_has_studied_from_is_absent(client, user, notebook):
    Notebook.objects.create(user=user, title='Untouched')
    _card(user, notebook, [notebook.sources.first()])

    titles = _by_title(client.get(URL))

    assert 'Biology' in titles and titles['Biology']['accuracy'] is None
    assert 'Untouched' not in titles


def test_weakest_notebook_comes_first(client, user, notebook):
    strong = Notebook.objects.create(user=user, title='History')
    from tests.conftest import make_source
    hist = make_source(strong, 'Rome')
    _card(user, notebook, [notebook.sources.first()], grades=['hard', 'hard', 'good'])
    _card(user, strong, [hist], grades=['good', 'good', 'good'])

    order = [n['title'] for n in client.get(URL).json()['weak_notebooks']]

    assert order == ['Biology', 'History']


def test_another_users_study_record_is_invisible(client, other_user):
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    from tests.conftest import make_source
    _card(other_user, theirs, [make_source(theirs, 'X')], grades=['good'])

    assert client.get(URL).json()['weak_notebooks'] == []
