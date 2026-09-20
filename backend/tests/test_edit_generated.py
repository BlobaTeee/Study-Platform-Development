"""Fixing what the AI got wrong: a student edits or deletes their own cards
and questions — and only their own, public or not."""
import pytest
from django.utils import timezone

from flashcards.models import Flashcard
from quizzes.models import MockTest, MockTestQuestion, Question, Quiz

pytestmark = pytest.mark.django_db


def _card(user, **kw):
    return Flashcard.objects.create(user=user, question='Q', answer='A', **kw)


def _question(user, **kw):
    quiz = Quiz.objects.create(user=user, title='Quiz', is_published=True, **kw)
    return Question.objects.create(quiz=quiz, question_text='Capital of France?',
                                   question_type='multiple_choice',
                                   options=['Paris', 'Rome', 'Oslo', 'Bern'], correct_answer='Paris')


# ---- flashcards -------------------------------------------------------------------

def test_a_student_fixes_their_own_card(client, user):
    card = _card(user)
    res = client.patch(f'/api/flashcards/flashcards/{card.id}/', {'answer': 'Better A'}, format='json')
    assert res.status_code == 200
    card.refresh_from_db()
    assert card.answer == 'Better A'


def test_a_student_deletes_their_own_card(client, user):
    card = _card(user)
    assert client.delete(f'/api/flashcards/flashcards/{card.id}/').status_code == 204
    assert not Flashcard.objects.filter(id=card.id).exists()


def test_someone_elses_public_card_can_be_read_but_not_changed(client, other_user):
    card = _card(other_user, is_public=True)
    assert client.get(f'/api/flashcards/flashcards/{card.id}/').status_code == 200
    assert client.patch(f'/api/flashcards/flashcards/{card.id}/', {'answer': 'x'}, format='json').status_code == 404
    assert client.delete(f'/api/flashcards/flashcards/{card.id}/').status_code == 404
    card.refresh_from_db()
    assert card.answer == 'A'


# ---- quiz questions ---------------------------------------------------------------

def test_a_student_fixes_their_own_question(client, user):
    q = _question(user)
    res = client.patch(f'/api/quizzes/questions/{q.id}/',
                       {'options': ['Paris', 'Lyon', 'Oslo', 'Bern'], 'correct_answer': 'Paris',
                        'explanation': 'Since 508.'}, format='json')
    assert res.status_code == 200, res.json()
    q.refresh_from_db()
    assert q.options[1] == 'Lyon' and q.explanation == 'Since 508.'


def test_the_correct_answer_must_be_one_of_the_options(client, user):
    q = _question(user)
    res = client.patch(f'/api/quizzes/questions/{q.id}/', {'correct_answer': 'Madrid'}, format='json')
    assert res.status_code == 400
    assert 'correct_answer' in res.json()


def test_a_question_cannot_be_moved_into_someone_elses_quiz(client, user, other_user):
    q = _question(user)
    theirs = Quiz.objects.create(user=other_user, title='Theirs')
    res = client.patch(f'/api/quizzes/questions/{q.id}/', {'quiz': theirs.id}, format='json')
    assert res.status_code == 400
    q.refresh_from_db()
    assert q.quiz.user == user


def test_someone_elses_public_quiz_cannot_be_changed(client, other_user):
    quiz = Quiz.objects.create(user=other_user, title='Theirs', is_public=True, is_published=True)
    assert client.get(f'/api/quizzes/quizzes/{quiz.id}/').status_code == 200
    assert client.patch(f'/api/quizzes/quizzes/{quiz.id}/', {'title': 'Mine now'}, format='json').status_code == 404
    assert client.delete(f'/api/quizzes/quizzes/{quiz.id}/').status_code == 404


def test_deleting_a_question_leaves_a_sat_paper_readable(client, user, notebook):
    q = _question(user)
    test = MockTest.objects.create(user=user, notebook=notebook, question_count=1, duration_minutes=5,
                                   completed_at=timezone.now(), score=100)
    MockTestQuestion.objects.create(mock_test=test, question=q, order=0, question_text=q.question_text,
                                    options=q.options, correct_answer='Paris', user_answer='Paris',
                                    is_correct=True)

    assert client.delete(f'/api/quizzes/questions/{q.id}/').status_code == 204

    review = client.post(f'/api/quizzes/mock-tests/{test.id}/submit/').json()
    assert review['paper'][0]['question_text'] == 'Capital of France?'
