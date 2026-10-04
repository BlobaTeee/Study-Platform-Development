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


# ---- 3. môn sắp thi đi trước ---------------------------------------------------------

def _plan_test(user, notebook, days_ahead):
    from quizzes.models import PlannedTest
    return PlannedTest.objects.create(
        user=user, notebook=notebook,
        scheduled_for=timezone.now() + timedelta(days=days_ahead))


def test_a_notebook_with_a_test_this_week_goes_first(client, user, notebook):
    other = Notebook.objects.create(user=user, title='History')
    make_source(other, 'Wars')
    older_debt = _cards(user, other, 3, prefix='history')
    for card in older_debt:
        _owe(user, card, days_overdue=20)
    exam = _cards(user, notebook, 2, prefix='biology')
    for card in exam:
        _owe(user, card, days_overdue=1)
    _plan_test(user, notebook, days_ahead=3)

    ids = _ids(client.get(DUE))

    # Three a day: both exam cards first, then the oldest other debt.
    assert ids[:2] == [exam[0].id, exam[1].id]
    assert ids[2] in {c.id for c in older_debt}


def test_each_queued_card_says_how_far_its_test_is(client, user, notebook):
    card = _cards(user, notebook, 1)[0]
    _owe(user, card)
    _plan_test(user, notebook, days_ahead=2)

    body = client.get(DUE).json()
    rows = body['results'] if isinstance(body, dict) else body

    assert rows[0]['exam_in_days'] == 2


def test_a_test_already_sat_gives_no_priority(client, user, notebook):
    other = Notebook.objects.create(user=user, title='History')
    make_source(other, 'Wars')
    older = _cards(user, other, 1, prefix='history')[0]
    _owe(user, older, days_overdue=20)
    sat = _cards(user, notebook, 1, prefix='biology')[0]
    _owe(user, sat, days_overdue=1)
    _plan_test(user, notebook, days_ahead=-1)

    assert _ids(client.get(DUE))[0] == older.id


def test_someone_elses_test_does_not_reorder_my_queue(client, user, other_user, notebook):
    other = Notebook.objects.create(user=user, title='History')
    make_source(other, 'Wars')
    older = _cards(user, other, 1, prefix='history')[0]
    _owe(user, older, days_overdue=20)
    mine = _cards(user, notebook, 1, prefix='biology')[0]
    _owe(user, mine, days_overdue=1)
    _plan_test(other_user, notebook, days_ahead=2)

    assert _ids(client.get(DUE))[0] == older.id


def test_the_summary_names_the_test_being_put_first(client, user, notebook):
    _owe(user, _cards(user, notebook, 1)[0])
    _plan_test(user, notebook, days_ahead=3)

    due = client.get('/api/analytics/sessions/recommendations/').json()['due']

    assert due['exams_first'] == [{'notebook_id': notebook.id, 'title': notebook.title, 'days': 3}]


def test_no_test_this_week_means_no_exam_line(client, user, notebook):
    _owe(user, _cards(user, notebook, 1)[0])
    _plan_test(user, notebook, days_ahead=12)

    due = client.get('/api/analytics/sessions/recommendations/').json()['due']

    assert due['exams_first'] == []


def test_a_test_for_a_notebook_with_nothing_to_study_is_not_named(client, user, notebook):
    # "Putting Biology first" means nothing when Biology owes no cards.
    _plan_test(user, notebook, days_ahead=2)

    due = client.get('/api/analytics/sessions/recommendations/').json()['due']

    assert due['exams_first'] == []


# ---- dashboard và hàng đợi phải nói cùng một con số ------------------------------------

def test_a_members_summary_counts_the_shared_cards_the_queue_offers(
        other_client, user, shared_notebook):
    # Thành viên học thẻ của notebook chung; nếu dashboard chỉ đếm thẻ của
    # chính họ thì nó báo 0 trong khi trang học đưa ra 2 thẻ.
    _cards(user, shared_notebook, 2)

    due = other_client.get('/api/analytics/sessions/recommendations/').json()['due']
    queue = _ids(other_client.get(DUE))

    assert due['today'] == len(queue) == 2


# ---- thẻ mới của môn thi: chia đều tới ngày thi -------------------------------------

def _subject(user, title, new_cards):
    nb = Notebook.objects.create(user=user, title=title)
    make_source(nb, title)
    return nb, _cards(user, nb, new_cards, prefix=title)


def _in_debt(user, notebook):
    """More owed than the day's 3 reviews: ordinary new cards are paused."""
    for card in _cards(user, notebook, 5, prefix='owed'):
        _owe(user, card, days_overdue=10)


def test_several_tests_on_one_day_each_bring_their_new_cards(client, user, notebook):
    _in_debt(user, notebook)
    bio, bio_cards = _subject(user, 'Biology', 6)
    chem, chem_cards = _subject(user, 'Chemistry', 6)
    _plan_test(user, bio, days_ahead=3)
    _plan_test(user, chem, days_ahead=3)

    ids = set(_ids(client.get(DUE)))

    # In debt, yet each test's six unseen cards come two a day for three days.
    assert len(ids & {c.id for c in bio_cards}) == 2
    assert len(ids & {c.id for c in chem_cards}) == 2


def test_a_test_tomorrow_brings_all_its_new_cards_today(client, user, notebook):
    _in_debt(user, notebook)
    bio, bio_cards = _subject(user, 'Biology', 6)
    _plan_test(user, bio, days_ahead=1)

    ids = set(_ids(client.get(DUE)))

    assert {c.id for c in bio_cards} <= ids


def test_new_cards_of_subjects_without_a_test_stay_paused(client, user, notebook):
    _in_debt(user, notebook)
    bio, _ = _subject(user, 'Biology', 3)
    _, history_cards = _subject(user, 'History', 3)
    _plan_test(user, bio, days_ahead=3)

    ids = set(_ids(client.get(DUE)))

    assert not ids & {c.id for c in history_cards}


def test_the_pace_does_not_grow_when_the_page_is_reopened(client, user, notebook):
    _in_debt(user, notebook)
    bio, bio_cards = _subject(user, 'Biology', 6)
    _plan_test(user, bio, days_ahead=3)
    for card_id in [i for i in _ids(client.get(DUE)) if i in {c.id for c in bio_cards}]:
        _record(client, Flashcard.objects.get(id=card_id))

    ids = set(_ids(client.get(DUE)))

    # Today's two are learned; the other four wait for the next two days.
    assert not ids & {c.id for c in bio_cards}


def test_the_summary_counts_and_names_every_test(client, user, notebook):
    _in_debt(user, notebook)
    bio, _ = _subject(user, 'Biology', 6)
    chem, _ = _subject(user, 'Chemistry', 6)
    _plan_test(user, bio, days_ahead=3)
    _plan_test(user, chem, days_ahead=5)

    due = client.get('/api/analytics/sessions/recommendations/').json()['due']

    # 3 reviews, 2 Biology (6 over 3 days), 2 Chemistry (6 over 5 days, rounded up).
    assert due['today'] == 3 + 2 + 2
    assert [e['title'] for e in due['exams_first']] == ['Biology', 'Chemistry']
    # Every new card belongs to a test: they are paced, not paused.
    assert due['new_paused'] is False


def test_the_summary_and_the_queue_agree_with_tests_in_play(client, user, notebook):
    _in_debt(user, notebook)
    bio, _ = _subject(user, 'Biology', 6)
    _subject(user, 'History', 4)
    _plan_test(user, bio, days_ahead=2)

    due = client.get('/api/analytics/sessions/recommendations/').json()['due']

    assert due['today'] == len(_ids(client.get(DUE)))
