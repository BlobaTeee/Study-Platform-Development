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


# ---- activity: the last fourteen days --------------------------------------

ACTIVITY = '/api/analytics/sessions/activity/'


def _review_at(user, notebook, when, result='good'):
    card = Flashcard.objects.create(user=user, notebook=notebook, question='q', answer='a')
    review = CardReview.objects.create(user=user, flashcard=card, result=result)
    CardReview.objects.filter(id=review.id).update(review_date=when)   # auto_now_add otherwise
    return review


def test_activity_has_fourteen_days_ending_today(client):
    from django.utils import timezone
    days = client.get(ACTIVITY).json()['days']
    assert len(days) == 14
    assert days[-1]['date'] == timezone.localdate().isoformat()
    assert all(d['reviews'] == 0 and d['accuracy'] is None for d in days)


def test_a_review_is_dated_in_the_students_zone_not_the_servers(client, user, notebook, settings):
    from datetime import datetime, timezone as tz
    settings.TIME_ZONE = 'Asia/Ho_Chi_Minh'
    user.profile.timezone = 'Europe/London'
    user.profile.save(update_fields=['timezone'])
    # 20:00 UTC on the 15th: 21:00 in London (still the 15th), 03:00 on the
    # 16th in Ho Chi Minh. The student is in London.
    _review_at(user, notebook, datetime(2026, 9, 15, 20, 0, tzinfo=tz.utc))
    import analytics.views as views
    monkey_today = datetime(2026, 9, 16, 12, 0, tzinfo=tz.utc)
    orig = views.timezone.now
    views.timezone.now = lambda: monkey_today
    try:
        days = {d['date']: d for d in client.get(ACTIVITY).json()['days']}
    finally:
        views.timezone.now = orig

    assert days['2026-09-15']['reviews'] == 1
    assert days['2026-09-16']['reviews'] == 0


def test_activity_counts_mock_tests_and_summarises(client, user, notebook):
    from django.utils import timezone
    from quizzes.models import MockTest
    _review_at(user, notebook, timezone.now(), 'good')
    _review_at(user, notebook, timezone.now(), 'hard')
    MockTest.objects.create(user=user, notebook=notebook, question_count=5,
                            duration_minutes=10, completed_at=timezone.now(), score=40.0)
    MockTest.objects.create(user=user, notebook=notebook, question_count=5,
                            duration_minutes=10)   # unfinished: not an event

    res = client.get(ACTIVITY).json()

    today = res['days'][-1]
    assert (today['reviews'], today['correct'], today['accuracy']) == (2, 1, 50.0)
    assert today['mock_scores'] == [40.0]
    assert res['summary'] == {'reviews': 2, 'accuracy': 50.0, 'mock_tests': 1}


def test_seed_reviews_do_not_count_as_study(client, user, notebook):
    from django.utils import timezone
    card = Flashcard.objects.create(user=user, notebook=notebook, question='q', answer='a')
    CardReview.objects.create(user=user, flashcard=card, result='good', is_seed=True)

    assert client.get(ACTIVITY).json()['summary']['reviews'] == 0


def test_activity_is_the_users_own(client, other_user):
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    _review_at(other_user, theirs, __import__('django.utils.timezone', fromlist=['now']).now())

    assert client.get(ACTIVITY).json()['summary']['reviews'] == 0
