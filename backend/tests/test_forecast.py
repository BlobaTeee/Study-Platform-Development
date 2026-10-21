"""Dự báo trí nhớ: how many studied cards will still be remembered on test day.

Per notebook, from each card's review history, FSRS gives the chance it is recalled now and on the day of the
next planned test (a week ahead when none is planned). It also picks the
cards whose review today would raise that the most, and says what the count
would become. Cards never studied are counted apart: there is nothing to
forecast for them.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from flashcards.models import Flashcard
from quizzes.models import PlannedTest
from study_sessions.models import CardReview

pytestmark = pytest.mark.django_db

URL = '/api/study/forecast/'
def _card(user, notebook, q):
    return Flashcard.objects.create(user=user, notebook=notebook, question=q, answer='a')


def _review(user, card, result, days_ago):
    r = CardReview.objects.create(user=user, flashcard=card, result=result)
    CardReview.objects.filter(pk=r.pk).update(review_date=timezone.now() - timedelta(days=days_ago))


def _forecast(client):
    res = client.get(URL)
    assert res.status_code == 200, res.content
    return res.json()['notebooks']


def test_a_notebook_without_a_planned_test_looks_a_week_ahead(client, user, notebook):
    card = _card(user, notebook, 'Q1?')
    _review(user, card, 'good', days_ago=1)

    nb = _forecast(client)[0]

    assert nb['notebook_id'] == notebook.id
    assert nb['has_exam'] is False and nb['days_ahead'] == 7
    assert nb['studied'] == 1
    assert 0 <= nb['at_exam'] <= nb['now'] <= 1


def test_a_planned_test_sets_the_day(client, user, notebook):
    card = _card(user, notebook, 'Q1?')
    _review(user, card, 'good', days_ago=1)
    PlannedTest.objects.create(user=user, notebook=notebook, scheduled_for=timezone.now() + timedelta(days=12))

    nb = _forecast(client)[0]

    assert nb['has_exam'] is True and nb['days_ahead'] == 12


def test_counts_add_up_over_the_cards(client, user, notebook):
    strong = [_card(user, notebook, f'Strong {i}?') for i in range(6)]
    weak = [_card(user, notebook, f'Weak {i}?') for i in range(4)]
    for c in strong:
        for d in (20, 10, 3):
            _review(user, c, 'good', days_ago=d)
    for c in weak:
        _review(user, c, 'hard', days_ago=6)
    _card(user, notebook, 'Never studied?')

    nb = _forecast(client)[0]

    assert nb['studied'] == 10 and nb['unseen'] == 1
    assert nb['now'] > nb['at_exam']
    # The cards to review are the ones a review today helps most by test day,
    # and reviewing them raises the count.
    suggested = set(nb['suggestion']['card_ids'])
    assert suggested and suggested <= {c.id for c in weak + strong}
    assert nb['suggestion']['at_exam'] > nb['at_exam']


def test_the_suggestion_is_the_cards_a_review_helps_most(user, notebook):
    from study_sessions.forecast import forecast
    from study_sessions.views import studiable_cards
    fading = _card(user, notebook, 'Fading?')          # learned once, two weeks ago
    _review(user, fading, 'good', days_ago=14)
    fresh = _card(user, notebook, 'Fresh?')            # well practised, reviewed today
    for d in (30, 10, 0):
        _review(user, fresh, 'good', days_ago=d)

    nb = forecast(user, studiable_cards(user))[0]

    assert nb['suggestion']['card_ids'][0] == fading.id
    assert fresh.id not in nb['suggestion']['card_ids']


def test_only_my_own_reviews_count(client, other_client, user, notebook):
    card = _card(user, notebook, 'Q1?')
    _review(user, card, 'good', days_ago=1)

    assert other_client.get(URL).json()['notebooks'] == []


def test_a_notebook_with_nothing_studied_is_left_out(client, user, notebook):
    _card(user, notebook, 'Never studied?')
    assert _forecast(client) == []


def test_retrievability_today_covers_only_reviewed_cards(user, notebook):
    from flashcards.models import Flashcard
    from study_sessions.forecast import retrievability_today
    from study_sessions.models import CardReview
    seen = Flashcard.objects.create(user=user, notebook=notebook, question='Q1?', answer='A')
    unseen = Flashcard.objects.create(user=user, notebook=notebook, question='Q2?', answer='A')
    CardReview.record(user, seen, 'good')

    got = retrievability_today(user, [seen.id, unseen.id])

    assert set(got) == {seen.id} and 0.9 < got[seen.id] <= 1.0
