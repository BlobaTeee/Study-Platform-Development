"""Starting a mock test from a plan: not before its time, not twice, not
someone else's."""
from datetime import timedelta

import pytest
from django.utils import timezone

from quizzes.models import MockTest, PlannedTest, Quiz, Question

pytestmark = pytest.mark.django_db

URL = '/api/quizzes/mock-tests/'


def _plan(user, notebook, **overrides):
    fields = dict(user=user, notebook=notebook, question_count=5, duration_minutes=10,
                  scheduled_for=timezone.now() - timedelta(minutes=1))
    fields.update(overrides)
    return PlannedTest.objects.create(**fields)


def _questions(user, notebook, n=5):
    """A quiz with `n` questions linked to the notebook's sources, so a paper
    can be drawn without generating anything."""
    quiz = Quiz.objects.create(user=user, title='Pool', is_published=True)
    quiz.sources.set(notebook.sources.all())
    for i in range(n):
        Question.objects.create(
            quiz=quiz, question_text=f'Q{i}?', question_type='multiple_choice',
            options=['a', 'b', 'c', 'd'], correct_answer='a', order=i)
    return quiz


def _start(client, notebook, plan):
    return client.post(URL, {
        'notebook': notebook.id, 'question_count': 5, 'duration_minutes': 10,
        'planned_test': plan.id,
    }, format='json')


def test_a_plan_cannot_be_started_before_its_scheduled_time(client, user, notebook):
    plan = _plan(user, notebook, scheduled_for=timezone.now() + timedelta(hours=2))

    res = _start(client, notebook, plan)

    assert res.status_code == 400
    assert res.json()['opens_at'] == plan.scheduled_for.isoformat()
    assert 'opens at' in res.json()['detail']
    assert MockTest.objects.count() == 0


def test_a_plan_starts_once_its_time_has_come(client, user, notebook):
    _questions(user, notebook)
    plan = _plan(user, notebook)

    res = _start(client, notebook, plan)

    assert res.status_code == 201, res.json()
    plan.refresh_from_db()
    assert plan.mock_test_id == res.json()['id']
    assert plan.sat_at is not None


def test_a_sat_plan_cannot_be_started_again(client, user, notebook):
    _questions(user, notebook)
    plan = _plan(user, notebook)
    assert _start(client, notebook, plan).status_code == 201

    res = _start(client, notebook, plan)

    assert res.status_code == 400
    assert 'already been sat' in res.json()['detail']
    assert MockTest.objects.count() == 1


def test_someone_elses_plan_looks_like_no_plan_at_all(client, other_user, notebook):
    # A 404, not a 403: the response must not reveal that the id exists.
    theirs = _plan(other_user, notebook)

    res = _start(client, notebook, theirs)

    assert res.status_code == 404
    assert MockTest.objects.count() == 0
