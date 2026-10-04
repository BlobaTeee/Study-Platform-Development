"""A shared notebook: the material is everyone's, the studying is your own."""
import pytest
from django.utils import timezone

from flashcards.models import Flashcard
from notebooks.models import NotebookMember
from quizzes.models import Question, Quiz
from study_sessions.models import CardReview

pytestmark = pytest.mark.django_db


def _card(owner, notebook, question='Quang hợp là gì?'):
    card = Flashcard.objects.create(user=owner, notebook=notebook, question=question, answer='A')
    card.sources.set(notebook.sources.all())
    return card


def _quiz(owner, notebook, title='Quiz'):
    quiz = Quiz.objects.create(user=owner, title=title, is_published=True)
    quiz.sources.set(notebook.sources.all())
    Question.objects.create(quiz=quiz, question_text='Q?', question_type='multiple_choice',
                            options=['a', 'b', 'c', 'd'], correct_answer='a')
    return quiz


# ---- reading shared material --------------------------------------------------------

def test_a_member_opens_the_notebook_and_its_documents(other_client, shared_notebook):
    body = other_client.get(f'/api/notebooks/notebooks/{shared_notebook.id}/').json()
    assert body['title'] == shared_notebook.title
    assert len(body['sources']) == shared_notebook.sources.count()
    src = shared_notebook.sources.first()
    assert other_client.get(f'/api/notebooks/sources/{src.id}/').status_code == 200


def test_a_member_studies_the_decks_and_quizzes_already_there(other_client, user, shared_notebook):
    card = _card(user, shared_notebook)
    quiz = _quiz(user, shared_notebook)

    cards = other_client.get('/api/flashcards/flashcards/').json()
    quizzes = other_client.get('/api/quizzes/quizzes/').json()

    assert card.id in {c['id'] for c in (cards['results'] if isinstance(cards, dict) else cards)}
    assert quiz.id in {q['id'] for q in (quizzes['results'] if isinstance(quizzes, dict) else quizzes)}


def test_a_stranger_sees_none_of_it(other_client, user, notebook):
    _card(user, notebook)
    _quiz(user, notebook)
    assert other_client.get(f'/api/notebooks/notebooks/{notebook.id}/').status_code == 404
    cards = other_client.get('/api/flashcards/flashcards/').json()
    assert (cards['results'] if isinstance(cards, dict) else cards) == []


# ---- studying stays private ---------------------------------------------------------

def test_two_members_keep_their_own_schedules(client, other_client, user, other_user, shared_notebook):
    card = _card(user, shared_notebook)

    res = client.post('/api/study/card-reviews/record/', {'flashcard_id': card.id, 'result': 'easy'}, format='json')
    assert res.status_code == 201, res.json()

    assert CardReview.objects.filter(user=user, flashcard=card).exists()
    assert not CardReview.objects.filter(user=other_user).exists()
    # The card is still owed for the other member.
    due = other_client.get('/api/study/card-reviews/due_today/').json()
    assert card.id in {c['id'] for c in (due['results'] if isinstance(due, dict) else due)}


def test_a_members_mistake_bank_is_their_own(client, other_client, user, shared_notebook):
    quiz = _quiz(user, shared_notebook)
    question = quiz.questions.first()
    from quizzes.models import MockTest, MockTestQuestion
    test = MockTest.objects.create(user=user, notebook=shared_notebook, question_count=1,
                                   duration_minutes=5, completed_at=timezone.now(), score=0)
    MockTestQuestion.objects.create(mock_test=test, question=question, order=0,
                                    question_text=question.question_text, options=question.options,
                                    correct_answer='a', user_answer='b', is_correct=False)

    assert client.get(f'/api/quizzes/mistakes/?notebook={shared_notebook.id}').json()['count'] == 1
    assert other_client.get(f'/api/quizzes/mistakes/?notebook={shared_notebook.id}').json()['count'] == 0


def test_a_member_can_sit_a_mock_test_on_shared_material(other_client, user, shared_notebook):
    quiz = _quiz(user, shared_notebook)
    for i in range(5):
        Question.objects.create(quiz=quiz, question_text=f'Q{i}?', question_type='multiple_choice',
                                options=['a', 'b', 'c', 'd'], correct_answer='a', order=i + 1)

    res = other_client.post('/api/quizzes/mock-tests/', {'notebook': shared_notebook.id,
                                                          'question_count': 5, 'duration_minutes': 10},
                            format='json')
    assert res.status_code == 201, res.json()
    assert res.json()['question_count'] == 5


# ---- writing ------------------------------------------------------------------------

def test_a_member_adds_a_document_and_generates_from_it(other_client, shared_notebook):
    words = ' '.join(f'word{i}' for i in range(60))
    res = other_client.post(f'/api/notebooks/notebooks/{shared_notebook.id}/add_text/',
                            {'title': 'Ghi chú của tôi', 'text': words}, format='json')
    assert res.status_code == 201, res.json()
    assert shared_notebook.sources.filter(title='Ghi chú của tôi').exists()


def test_a_member_cannot_rename_or_delete_the_notebook(other_client, shared_notebook):
    assert other_client.patch(f'/api/notebooks/notebooks/{shared_notebook.id}/',
                              {'title': 'Của tôi'}, format='json').status_code == 403
    assert other_client.delete(f'/api/notebooks/notebooks/{shared_notebook.id}/').status_code == 403
    shared_notebook.refresh_from_db()
    assert shared_notebook.title == 'Biology'


def test_a_member_cannot_edit_someone_elses_card_but_the_owner_can(client, other_client, user, shared_notebook):
    card = _card(user, shared_notebook)
    assert other_client.patch(f'/api/flashcards/flashcards/{card.id}/', {'answer': 'x'}, format='json').status_code == 403
    assert client.patch(f'/api/flashcards/flashcards/{card.id}/', {'answer': 'Ok'}, format='json').status_code == 200
    card.refresh_from_db()
    assert card.answer == 'Ok'


def test_the_owner_may_edit_a_members_card(client, other_user, shared_notebook):
    card = _card(other_user, shared_notebook)
    assert client.patch(f'/api/flashcards/flashcards/{card.id}/', {'answer': 'Fixed'}, format='json').status_code == 200


def test_a_member_may_edit_their_own_card(other_client, other_user, shared_notebook):
    card = _card(other_user, shared_notebook)
    assert other_client.patch(f'/api/flashcards/flashcards/{card.id}/', {'answer': 'Mine'}, format='json').status_code == 200
