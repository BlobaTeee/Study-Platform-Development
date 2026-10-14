"""seed_demo: a demo account with weeks of believable study behind it.

For a live demo the progress features need history: a study calendar,
cards forgotten and remembered, mock tests with wrong answers, a test
coming up. The command builds that for one named account from SciQ (real
science questions with their supporting passages), with no AI request, and
never touches another account.
"""
from datetime import timedelta

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from flashcards.models import Flashcard
from notebooks.models import Notebook, Source
from quizzes.models import MockTest, MockTestQuestion, PlannedTest, Question
from study_sessions.models import CardReview

pytestmark = pytest.mark.django_db


@pytest.fixture
def no_ai(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('seed_demo must not call a model')
    for target in ('notebooks.services.generate.get_ai_provider', 'notebooks.services.key_points.get_ai_provider',
                   'notebooks.services.ai_provider.get_ai_provider'):
        monkeypatch.setattr(target, refuse)


def _seed(user, **kw):
    call_command('seed_demo', email=user.email, days=kw.pop('days', 14), **kw)


def test_it_builds_notebooks_documents_cards_and_quizzes(user, no_ai):
    _seed(user)

    notebooks = Notebook.objects.filter(user=user)
    assert notebooks.count() == 3
    sources = Source.objects.filter(notebook__user=user)
    assert sources.count() == 6
    assert all(s.status == 'ready' and len(s.extracted_text) > 1500 for s in sources)
    assert Flashcard.objects.filter(user=user, archived=False).count() >= 50
    assert Flashcard.objects.filter(user=user, kind='cloze').exists()
    questions = Question.objects.filter(quiz__user=user, quiz__is_published=True)
    assert questions.count() >= 40
    assert all(len(q.options) == 4 and q.correct_answer in q.options and q.source_excerpt for q in questions)


def test_the_history_is_spread_over_past_days(user, no_ai):
    _seed(user, days=14)

    dates = {r.review_date.date() for r in CardReview.objects.filter(user=user)}
    now = timezone.now()
    assert len(dates) >= 8                                   # studied on most days, not all
    assert min(dates) >= (now - timedelta(days=15)).date()
    assert max(r.review_date for r in CardReview.objects.filter(user=user)) <= now


def test_some_cards_are_forgotten_and_a_test_is_coming(user, no_ai):
    _seed(user)

    latest = {}
    for r in CardReview.objects.filter(user=user).order_by('review_date'):
        latest[r.flashcard_id] = r.result
    assert 'hard' in latest.values() and 'good' in latest.values()
    assert PlannedTest.objects.filter(user=user, scheduled_for__gt=timezone.now(), sat_at__isnull=True).exists()
    sat = MockTest.objects.filter(user=user, completed_at__isnull=False)
    assert sat.count() >= 2
    wrong = MockTestQuestion.objects.filter(mock_test__in=sat, is_correct=False).exclude(user_answer='')
    assert wrong.count() >= 3


def test_an_account_with_its_own_notebooks_is_left_alone(user, no_ai):
    Notebook.objects.create(user=user, title='Mine')

    with pytest.raises(CommandError):
        _seed(user)

    assert list(Notebook.objects.filter(user=user).values_list('title', flat=True)) == ['Mine']


def test_reset_replaces_only_that_accounts_data(user, other_user, no_ai):
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    _seed(user)
    first = set(Notebook.objects.filter(user=user).values_list('id', flat=True))

    _seed(user, reset=True)

    assert Notebook.objects.filter(user=user).count() == 3
    assert not first & set(Notebook.objects.filter(user=user).values_list('id', flat=True))
    assert Notebook.objects.filter(id=theirs.id).exists()


def test_an_unknown_email_is_refused(db):
    with pytest.raises(CommandError):
        call_command('seed_demo', email='nobody@example.com')
