"""Phần của hôm nay: hàng đợi chỉ đưa ra lượng học được trong một ngày.

Nghỉ hai tuần là có hàng trăm thẻ đến hạn; hiện một con số như vậy là lúc
người học bỏ cuộc. Nên mỗi ngày có một phần, phần còn lại vẫn đến hạn và đứng
đầu hàng ngày mai, và thẻ mới chờ trong lúc còn nợ.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from flashcards.models import Flashcard
from notebooks.models import Notebook
from study_sessions.models import CardReview
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

DUE = '/api/study/card-reviews/due_today/'


@pytest.fixture(autouse=True)
def small_day(settings):
    settings.DAILY_REVIEW_LIMIT = 3
    settings.DAILY_NEW_LIMIT = 2


def _cards(user, notebook, n, prefix='Q'):
    out = []
    for i in range(n):
        card = Flashcard.objects.create(user=user, notebook=notebook,
                                        question=f'{prefix}{i}?', answer='A')
        card.sources.set(notebook.sources.all())
        out.append(card)
    return out


def _owe(user, card, days_overdue=1):
    """Mark a card as reviewed long ago and due `days_overdue` days back."""
    review = CardReview.objects.create(user=user, flashcard=card, result='good')
    when = timezone.now() - timedelta(days=days_overdue + 5)
    CardReview.objects.filter(pk=review.pk).update(
        review_date=when,
        next_review_date=timezone.localdate() - timedelta(days=days_overdue))


def _ids(res):
    body = res.json()
    return [c['id'] for c in (body['results'] if isinstance(body, dict) else body)]


def _record(client, card, result='good'):
    res = client.post('/api/study/card-reviews/record/',
                      {'flashcard_id': card.id, 'result': result}, format='json')
    assert res.status_code == 201, res.json()


# ---- 1. chỉ phần của hôm nay ---------------------------------------------------------

def test_the_queue_holds_only_todays_share(client, user, notebook):
    owed = _cards(user, notebook, 6)
    for i, card in enumerate(owed):
        _owe(user, card, days_overdue=i + 1)

    ids = _ids(client.get(DUE))

    # Three a day, most overdue first.
    assert ids == [owed[5].id, owed[4].id, owed[3].id]


def test_reviews_done_today_shrink_what_is_left(client, user, notebook):
    owed = _cards(user, notebook, 6)
    for card in owed:
        _owe(user, card)
    first = _ids(client.get(DUE))

    _record(client, Flashcard.objects.get(id=first[0]))
    _record(client, Flashcard.objects.get(id=first[1]))

    # Reopening the page does not hand out a fresh three.
    assert len(_ids(client.get(DUE))) == 1


def test_a_finished_day_shows_nothing_even_with_debt_left(client, user, notebook):
    owed = _cards(user, notebook, 5)
    for card in owed:
        _owe(user, card)
    for card_id in _ids(client.get(DUE)):
        _record(client, Flashcard.objects.get(id=card_id))

    assert _ids(client.get(DUE)) == []


# ---- 2. thẻ mới chờ khi còn nợ -------------------------------------------------------

def test_new_cards_wait_while_debt_exceeds_the_day(client, user, notebook):
    owed = _cards(user, notebook, 5, prefix='owed')
    for card in owed:
        _owe(user, card)
    fresh = _cards(user, notebook, 2, prefix='new')

    ids = _ids(client.get(DUE))

    assert not set(ids) & {c.id for c in fresh}


def test_new_cards_come_when_today_can_clear_the_debt(client, user, notebook):
    owed = _cards(user, notebook, 1, prefix='owed')
    _owe(user, owed[0])
    fresh = _cards(user, notebook, 4, prefix='new')

    ids = _ids(client.get(DUE))

    # One owed card, then the day's two new ones.
    assert ids == [owed[0].id, fresh[0].id, fresh[1].id]


def test_new_cards_learned_today_use_up_the_new_allowance(client, user, notebook):
    fresh = _cards(user, notebook, 4)
    _record(client, fresh[0])

    ids = _ids(client.get(DUE))

    assert len([i for i in ids if i in {c.id for c in fresh}]) == 1


# ---- học theo một tài liệu -----------------------------------------------------------

def test_studying_one_document_draws_from_that_document(client, user, notebook):
    # Lọc ở server trước khi chia phần, nếu không phần của hôm nay có thể toàn
    # thẻ của môn khác và notebook này sẽ báo "đã xong" dù vẫn còn thẻ đến hạn.
    other = Notebook.objects.create(user=user, title='History')
    make_source(other, 'Wars')
    elsewhere = _cards(user, other, 5, prefix='elsewhere')
    for card in elsewhere:
        _owe(user, card, days_overdue=30)          # older debt, would win globally
    here = _cards(user, notebook, 2, prefix='here')
    for card in here:
        _owe(user, card, days_overdue=1)
    source_ids = ','.join(str(s.id) for s in notebook.sources.all())

    ids = _ids(client.get(DUE, {'source': source_ids}))

    assert set(ids) == {c.id for c in here}


def test_one_document_still_respects_the_days_allowance(client, user, notebook):
    here = _cards(user, notebook, 6)
    for card in here:
        _owe(user, card)
    source_ids = ','.join(str(s.id) for s in notebook.sources.all())

    assert len(_ids(client.get(DUE, {'source': source_ids}))) == 3


# ---- trang tổng quan -----------------------------------------------------------------

def test_the_summary_tells_todays_share_and_what_waits(client, user, notebook):
    owed = _cards(user, notebook, 5, prefix='owed')
    for card in owed:
        _owe(user, card)
    _cards(user, notebook, 2, prefix='new')

    due = client.get('/api/analytics/sessions/recommendations/').json()['due']

    assert due['today'] == 3
    assert due['later'] == 2
    assert due['new_paused'] is True
    # The full counts stay, for anyone who wants the whole picture.
    assert due['due'] == 5 and due['new'] == 2
