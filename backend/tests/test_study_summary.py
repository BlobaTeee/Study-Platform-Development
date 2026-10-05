"""Một sổ tay nói được tình trạng ôn tập của chính nó, cho cả sổ.

The notebook page leads with what can be studied now across the whole
notebook: today's cards, how the quizzes have gone, and the latest quiz to
take. The numbers are the notebook's alone and agree with the study page the
"Study" button opens.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from flashcards.models import Flashcard
from notebooks.models import Notebook
from quizzes.models import Answer, Question, Quiz, QuizAttempt
from study_sessions.models import CardReview
from tests.conftest import make_source

pytestmark = pytest.mark.django_db


def _summary(client, notebook):
    res = client.get(f'/api/notebooks/notebooks/{notebook.id}/study_summary/')
    assert res.status_code == 200, res.content
    return res.json()


def _card(user, notebook, question='Q?'):
    card = Flashcard.objects.create(user=user, notebook=notebook, question=question, answer='A')
    card.sources.set(notebook.sources.all())
    return card


def _owe(user, card, days_overdue=1):
    review = CardReview.objects.create(user=user, flashcard=card, result='good')
    CardReview.objects.filter(pk=review.pk).update(
        review_date=timezone.now() - timedelta(days=days_overdue + 5),
        next_review_date=timezone.localdate() - timedelta(days=days_overdue))


def _schedule_ahead(user, card):
    review = CardReview.objects.create(user=user, flashcard=card, result='easy')
    CardReview.objects.filter(pk=review.pk).update(
        review_date=timezone.now() - timedelta(days=1),
        next_review_date=timezone.localdate() + timedelta(days=9))


def _quiz(user, notebook, questions=2):
    quiz = Quiz.objects.create(user=user, title='Quiz', is_published=True)
    quiz.sources.set(notebook.sources.all())
    made = [Question.objects.create(quiz=quiz, question_text=f'Q{i}?', question_type='multiple_choice',
                                    options=['a', 'b'], correct_answer='a') for i in range(questions)]
    return quiz, made


def _answer(user, quiz, question, correct):
    attempt = QuizAttempt.objects.create(quiz=quiz, user=user)
    Answer.objects.create(quiz_attempt=attempt, question=question,
                          user_answer='a' if correct else 'b', is_correct=correct)


def _other_notebook(user):
    nb = Notebook.objects.create(user=user, title='History')
    make_source(nb, 'Wars')
    return nb


# ---- thẻ ---------------------------------------------------------------------------

def test_counts_only_this_notebooks_cards(client, user, notebook):
    _card(user, notebook)
    _card(user, notebook)
    _card(user, _other_notebook(user))

    assert _summary(client, notebook)['cards'] == 2


def test_todays_cards_count_what_is_owed_and_skip_what_is_scheduled_ahead(client, user, notebook):
    _owe(user, _card(user, notebook, 'owed'))
    _schedule_ahead(user, _card(user, notebook, 'ahead'))

    summary = _summary(client, notebook)

    assert summary['due'] == 1
    assert summary['today'] == 1


def test_today_agrees_with_the_study_page_it_opens(client, user, notebook, settings):
    settings.DAILY_REVIEW_LIMIT = 3
    for i in range(5):
        _owe(user, _card(user, notebook, f'owed {i}'))
    _owe(user, _card(user, _other_notebook(user), 'elsewhere'))

    summary = _summary(client, notebook)
    queue = client.get('/api/study/card-reviews/due_today/', {'notebook': notebook.id}).json()
    queue = queue['results'] if isinstance(queue, dict) else queue

    assert summary['today'] == len(queue) == 3
    assert {c['notebook_id'] for c in queue} == {notebook.id}


# ---- bài kiểm tra ------------------------------------------------------------------

def test_accuracy_is_this_students_answers_on_this_notebooks_questions(client, user, notebook):
    quiz, (q1, q2) = _quiz(user, notebook)
    _answer(user, quiz, q1, correct=True)
    _answer(user, quiz, q2, correct=False)
    _answer(user, quiz, q2, correct=True)
    other_quiz, (oq, _) = _quiz(user, _other_notebook(user))
    _answer(user, other_quiz, oq, correct=False)

    summary = _summary(client, notebook)

    assert summary['questions'] == 2
    assert summary['accuracy'] == 67          # 2 of 3, this notebook only


def test_no_answers_yet_means_no_accuracy(client, user, notebook):
    _quiz(user, notebook)

    assert _summary(client, notebook)['accuracy'] is None


def test_the_latest_quiz_comes_with_its_sources_so_it_can_be_opened(client, user, notebook):
    older, _ = _quiz(user, notebook)
    newer, _ = _quiz(user, notebook)
    Quiz.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=3))

    latest = _summary(client, notebook)['latest_quiz']

    assert latest['id'] == newer.id
    assert sorted(latest['source_ids']) == sorted(notebook.sources.values_list('id', flat=True))


def test_an_empty_notebook_has_nothing_to_report(client, user):
    nb = Notebook.objects.create(user=user, title='Empty')

    assert _summary(client, nb) == {'cards': 0, 'due': 0, 'today': 0, 'questions': 0,
                                    'accuracy': None, 'latest_quiz': None}


# ---- ai được xem ----------------------------------------------------------------------

def test_a_member_sees_the_shared_material(other_client, user, shared_notebook):
    _card(user, shared_notebook)
    _quiz(user, shared_notebook)

    summary = _summary(other_client, shared_notebook)

    assert summary['cards'] == 1
    assert summary['latest_quiz'] is not None


def test_a_stranger_gets_nothing(other_client, notebook):
    res = other_client.get(f'/api/notebooks/notebooks/{notebook.id}/study_summary/')

    assert res.status_code == 404
