"""The mistake bank: what you got wrong, until you get it right twice."""
from datetime import timedelta

import pytest
from django.utils import timezone

from quizzes.models import Answer, MockTest, MockTestQuestion, Question, Quiz, QuizAttempt

pytestmark = pytest.mark.django_db


def _questions(user, notebook, n=6):
    quiz = Quiz.objects.create(user=user, title='Pool', is_published=True)
    quiz.sources.set(notebook.sources.all())
    return [Question.objects.create(quiz=quiz, question_text=f'Q{i}?', question_type='multiple_choice',
                                    options=['a', 'b', 'c', 'd'], correct_answer='a', order=i)
            for i in range(n)]


def _sit(user, notebook, verdicts, when=None):
    """A completed mock test: {question: is_correct}."""
    test = MockTest.objects.create(user=user, notebook=notebook, question_count=len(verdicts),
                                   duration_minutes=10, completed_at=when or timezone.now(), score=0)
    for i, (q, ok) in enumerate(verdicts.items()):
        MockTestQuestion.objects.create(mock_test=test, question=q, order=i, question_text=q.question_text,
                                        options=q.options, correct_answer=q.correct_answer,
                                        user_answer='a' if ok else 'b', is_correct=ok,
                                        answered_at=when or timezone.now())
    return test


def _bank(client, notebook):
    return client.get(f'/api/quizzes/mistakes/?notebook={notebook.id}').json()


def test_the_bank_is_empty_until_something_is_missed(client, user, notebook):
    qs = _questions(user, notebook)
    _sit(user, notebook, {qs[0]: True, qs[1]: True})
    assert _bank(client, notebook) == {'count': 0, 'questions': []}


def test_missed_questions_are_listed_without_their_answers(client, user, notebook):
    qs = _questions(user, notebook)
    _sit(user, notebook, {qs[0]: False, qs[1]: True, qs[2]: False})

    body = _bank(client, notebook)

    assert body['count'] == 2
    assert {q['id'] for q in body['questions']} == {qs[0].id, qs[2].id}
    assert 'correct_answer' not in body['questions'][0]


def test_quiz_answers_count_as_evidence_too(client, user, notebook):
    qs = _questions(user, notebook)
    attempt = QuizAttempt.objects.create(quiz=qs[0].quiz, user=user)
    Answer.objects.create(quiz_attempt=attempt, question=qs[3], user_answer='b', is_correct=False)
    assert {q['id'] for q in _bank(client, notebook)['questions']} == {qs[3].id}


def test_two_right_answers_in_a_row_clear_a_question(client, user, notebook):
    qs = _questions(user, notebook)
    t0 = timezone.now()
    _sit(user, notebook, {qs[0]: False}, when=t0)
    _sit(user, notebook, {qs[0]: True}, when=t0 + timedelta(hours=1))
    assert _bank(client, notebook)['count'] == 1        # one right is not enough
    _sit(user, notebook, {qs[0]: True}, when=t0 + timedelta(hours=2))
    assert _bank(client, notebook)['count'] == 0


def test_a_retake_paper_holds_only_the_owed_questions(client, user, notebook):
    qs = _questions(user, notebook)
    _sit(user, notebook, {qs[0]: False, qs[1]: True, qs[2]: False, qs[3]: False})

    res = client.post('/api/quizzes/mock-tests/', {'notebook': notebook.id, 'mistakes_only': True,
                                                   'duration_minutes': 10}, format='json')

    assert res.status_code == 201, res.json()
    paper_qids = set(MockTestQuestion.objects.filter(mock_test_id=res.json()['id'])
                     .values_list('question_id', flat=True))
    assert paper_qids == {qs[0].id, qs[2].id, qs[3].id}
    assert res.json()['question_count'] == 3


def test_a_retake_with_an_empty_bank_is_refused_plainly(client, user, notebook):
    _questions(user, notebook)
    res = client.post('/api/quizzes/mock-tests/', {'notebook': notebook.id, 'mistakes_only': True},
                      format='json')
    assert res.status_code == 400
    assert 'mistake' in res.json()['detail'].lower() or 'nothing' in res.json()['detail'].lower()


def test_the_bank_is_scoped_to_the_notebook_and_the_user(client, user, other_user, notebook):
    from notebooks.models import Notebook
    from tests.conftest import make_source
    qs = _questions(user, notebook)
    _sit(user, notebook, {qs[0]: False})
    other_nb = Notebook.objects.create(user=user, title='Other'); make_source(other_nb, 'X')
    assert _bank(client, other_nb)['count'] == 0
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    assert client.get(f'/api/quizzes/mistakes/?notebook={theirs.id}').status_code == 404


def test_the_summary_counts_what_is_owed_in_every_notebook(client, user, other_user, notebook):
    from notebooks.models import Notebook
    qs = _questions(user, notebook)
    _sit(user, notebook, {qs[0]: False, qs[1]: False, qs[2]: True})
    Notebook.objects.create(user=user, title='Nothing missed here')
    _sit(other_user, notebook, {qs[3]: False})            # someone else's miss

    body = client.get('/api/quizzes/mistakes/summary/').json()

    assert body == {'notebooks': [{'notebook_id': notebook.id, 'title': notebook.title, 'count': 2}]}


def test_the_home_page_hears_of_missed_questions_and_problems_due(client, user, notebook):
    """Not cards alone: questions waiting to be redone and practice problems
    due again are counted beside them (2026-11-25)."""
    from exercises.models import Exercise
    qs = _questions(user, notebook)
    _sit(user, notebook, {qs[0]: False, qs[1]: False, qs[2]: True})
    today = timezone.localdate()
    Exercise.objects.create(user=user, notebook=notebook, prompt='Due', reference={}, status='revisit',
                            revisit_on=today)
    Exercise.objects.create(user=user, notebook=notebook, prompt='Later', reference={}, status='revisit',
                            revisit_on=today + timedelta(days=3))

    body = client.get('/api/analytics/sessions/recommendations/').json()

    assert body['beyond_cards'] == {'owed': 2, 'practice_due': 1}


def test_missed_questions_are_redone_like_a_quiz(client, user, notebook):
    """One at a time, the answer straight after, no clock (2026-11-25). The
    list still shows no answers; two right in a row clear a question."""
    qs = _questions(user, notebook)
    _sit(user, notebook, {qs[0]: False, qs[1]: False})
    url = '/api/quizzes/mistakes/redo/'

    listed = client.get(f'{url}?notebook={notebook.id}').json()['questions']
    assert [q['id'] for q in listed] == [qs[0].id, qs[1].id]
    assert all('correct_answer' not in q for q in listed)

    first = client.post(url, {'notebook': notebook.id, 'question_id': qs[0].id, 'answer': 'a'}, format='json').json()
    assert first['is_correct'] and first['correct_answer'] == 'a' and not first['cleared']   # one right is luck
    second = client.post(url, {'notebook': notebook.id, 'question_id': qs[0].id, 'answer': 'a'}, format='json').json()
    assert second['cleared']
    wrong = client.post(url, {'notebook': notebook.id, 'question_id': qs[1].id, 'answer': 'b'}, format='json').json()
    assert not wrong['is_correct'] and not wrong['cleared']

    assert [q['id'] for q in client.get(f'{url}?notebook={notebook.id}').json()['questions']] == [qs[1].id]
    redo = QuizAttempt.objects.get(user=user, is_redo=True)          # one redo attempt for the day
    assert (redo.total_points, redo.is_completed) == (3, True)


def test_a_redo_only_takes_questions_of_ones_own_notebooks(client, other_user, notebook):
    from notebooks.models import Notebook
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    assert client.get(f'/api/quizzes/mistakes/redo/?notebook={theirs.id}').status_code == 404
    res = client.post('/api/quizzes/mistakes/redo/', {'notebook': notebook.id, 'question_id': 999999, 'answer': 'a'},
                      format='json')
    assert res.status_code == 404
