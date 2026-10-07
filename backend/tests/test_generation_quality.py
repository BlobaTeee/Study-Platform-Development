"""Regenerating a quiz replaces the previous one for the same selection.

(Flashcards no longer do: a deck grows instead, see test_add_more_cards.)
Quizzes used to be appended, so every regeneration stacked another quiz on the same sources and
the mock-test pool drew near-duplicate — and sometimes contradicting —
questions from all of them."""
import pytest

from notebooks.services.generate import retire_previous_quizzes
from quizzes.models import Question, Quiz
from quizzes.views import _question_pool

pytestmark = pytest.mark.django_db


def _quiz(user, sources, title='q', published=True):
    quiz = Quiz.objects.create(user=user, title=title, is_published=published)
    quiz.sources.set(sources)
    Question.objects.create(quiz=quiz, question_text=f'{title}?', question_type='multiple_choice',
                            options=['a', 'b'], correct_answer='a', order=0)
    return quiz


def test_the_previous_quiz_of_the_same_selection_is_retired(user, notebook):
    cells, _ = notebook.sources.order_by('id')
    old = _quiz(user, [cells], 'old')
    new = _quiz(user, [cells], 'new')

    retire_previous_quizzes(new, user, [cells.id])

    old.refresh_from_db(); new.refresh_from_db()
    assert (old.is_published, new.is_published) == (False, True)


def test_a_quiz_of_a_different_selection_is_left_alone(user, notebook):
    cells, genetics = notebook.sources.order_by('id')
    both = _quiz(user, [cells, genetics], 'both')
    new = _quiz(user, [cells], 'new')

    retire_previous_quizzes(new, user, [cells.id])

    both.refresh_from_db()
    assert both.is_published is True


def test_the_pool_only_draws_from_published_quizzes(user, notebook):
    cells, _ = notebook.sources.order_by('id')
    retired = _quiz(user, [cells], 'retired', published=False)
    live = _quiz(user, [cells], 'live')

    ids = {q['id'] for q in _question_pool(user, [cells.id])}

    assert ids == set(live.questions.values_list('id', flat=True))
    assert not ids & set(retired.questions.values_list('id', flat=True))


def test_the_quiz_list_hides_retired_quizzes(client, user, notebook):
    cells, _ = notebook.sources.order_by('id')
    _quiz(user, [cells], 'retired', published=False)
    live = _quiz(user, [cells], 'live')

    body = client.get('/api/quizzes/quizzes/').json()
    rows = body['results'] if isinstance(body, dict) else body

    assert [r['id'] for r in rows] == [live.id]


def test_material_counts_names_the_live_quiz(client, user, notebook):
    cells, _ = notebook.sources.order_by('id')
    _quiz(user, [cells], 'retired', published=False)
    live = _quiz(user, [cells], 'live')

    res = client.get(f'/api/notebooks/notebooks/{notebook.id}/material_counts/?source_ids={cells.id}')

    assert res.json()['quiz_id'] == live.id


def test_retired_quizzes_still_count_toward_mastery(client, user, notebook):
    # Answers on a retired quiz are still evidence of what the student knows.
    from quizzes.models import Answer, QuizAttempt
    cells, _ = notebook.sources.order_by('id')
    retired = _quiz(user, [cells], 'retired', published=False)
    attempt = QuizAttempt.objects.create(quiz=retired, user=user)
    q = retired.questions.first()
    Answer.objects.create(quiz_attempt=attempt, question=q, user_answer='a', is_correct=True)

    row = next(n for n in client.get('/api/analytics/sessions/recommendations/').json()['weak_notebooks']
               if n['title'] == 'Biology')

    assert row['reviews'] == 1 and row['accuracy'] == 100.0
