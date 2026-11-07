"""Typing an answer on a quiz: graded offline, the LLM only for the ambiguous
band, and the student's override recorded as a label."""
import pytest

from quizzes.models import Answer, Question, Quiz, QuizAttempt

pytestmark = pytest.mark.django_db


@pytest.fixture
def attempt(user):
    quiz = Quiz.objects.create(user=user, title='Gases', is_published=True)
    Question.objects.create(
        quiz=quiz, question_text='What gas do plants absorb during photosynthesis?',
        question_type='multiple_choice',
        options=['carbon dioxide', 'oxygen', 'nitrogen', 'argon'],
        correct_answer='carbon dioxide', order=0,
        explanation='Plants absorb carbon dioxide during photosynthesis.')
    return QuizAttempt.objects.create(quiz=quiz, user=user)


def _grade(client, attempt, typed):
    q = attempt.quiz.questions.first()
    return client.post(f'/api/quizzes/attempts/{attempt.id}/grade_typed_answer/',
                       {'question_id': q.id, 'answer': typed}, format='json')


def test_an_exact_answer_is_correct_and_recorded_as_typed(client, attempt):
    res = _grade(client, attempt, 'The Carbon Dioxide')

    assert res.status_code == 200, res.json()
    body = res.json()
    assert (body['verdict'], body['how'], body['is_correct']) == ('correct', 'exact', True)
    assert body['reference_answer'] == 'carbon dioxide'
    row = Answer.objects.get(id=body['id'])
    assert (row.mode, row.verdict, row.graded_how, row.points_earned) == ('typed', 'correct', 'exact', 1)


def test_a_distractor_is_wrong_by_the_distractor_rule(client, attempt):
    body = _grade(client, attempt, 'oxygen').json()
    assert (body['verdict'], body['how']) == ('wrong', 'distractor')
    assert body['is_correct'] is False


def test_an_empty_answer_is_refused(client, attempt):
    res = _grade(client, attempt, '   ')
    assert res.status_code == 400
    assert Answer.objects.count() == 0


def test_a_question_from_another_quiz_is_not_found(client, user, attempt):
    other = Quiz.objects.create(user=user, title='Other')
    q = Question.objects.create(quiz=other, question_text='?', question_type='multiple_choice',
                                options=['a', 'b'], correct_answer='a', order=0)
    res = client.post(f'/api/quizzes/attempts/{attempt.id}/grade_typed_answer/',
                      {'question_id': q.id, 'answer': 'a'}, format='json')
    assert res.status_code == 404


def test_grading_is_refused_once_the_attempt_is_completed(client, attempt):
    QuizAttempt.objects.filter(id=attempt.id).update(is_completed=True)
    assert _grade(client, attempt, 'carbon dioxide').status_code == 400


def test_a_missing_scorer_artifact_is_a_503_not_a_crash(client, attempt, monkeypatch):
    import quizzes.services.typed_grading as tg
    def missing():
        raise FileNotFoundError('answer_scorer.joblib')
    monkeypatch.setattr(tg, 'get_answer_scorer', missing)

    res = _grade(client, attempt, 'some gas')

    assert res.status_code == 503
    assert 'ensure_ml_model' in res.json()['detail']
    assert Answer.objects.count() == 0


# ---- an answer typed in the page's language ---------------------------------------

def _translator(monkeypatch, said):
    seen = []
    def in_context(pairs, source, target):
        seen.extend(pairs)
        return [said for _ in pairs]
    monkeypatch.setattr('notebooks.services.translate.machine_translate_in_context', in_context)
    return seen


def test_an_answer_typed_in_vietnamese_counts_when_it_means_the_answer(client, attempt, monkeypatch):
    seen = _translator(monkeypatch, 'carbon dioxide')
    body = _grade(client, attempt, 'khí cacbonic').json()
    assert (body['verdict'], body['is_correct']) == ('correct', True)
    assert seen == [('khí cacbonic', 'What gas do plants absorb during photosynthesis?')]
    assert Answer.objects.get(id=body['id']).user_answer == 'khí cacbonic'


def test_a_vietnamese_answer_that_means_a_wrong_one_stays_wrong(client, attempt, monkeypatch):
    _translator(monkeypatch, 'oxygen')
    body = _grade(client, attempt, 'khí ôxi').json()
    assert (body['verdict'], body['is_correct']) == ('wrong', False)


def test_without_the_translator_a_vietnamese_answer_is_graded_as_typed(client, attempt):
    res = _grade(client, attempt, 'khí cacbonic')     # conftest: the model is not there
    assert res.status_code == 200
    assert res.json()['is_correct'] is False


# ---- the LLM tier ----------------------------------------------------------------

class _Provider:
    name = 'stub'
    def __init__(self, reply=None, raise_=None):
        self.reply, self.raise_, self.calls = reply, raise_, []
    def generate_json(self, prompt):
        self.calls.append(prompt)
        if self.raise_:
            raise self.raise_
        return self.reply
    def summarize(self, text, title=''):
        raise NotImplementedError


@pytest.fixture
def near_verdict(monkeypatch):
    """Force rules 1-3 to say `near`, so what happens next is the LLM tier's."""
    import quizzes.services.typed_grading as tg
    monkeypatch.setattr(tg, 'rules_grade',
                        lambda *a, **k: {'verdict': 'near', 'how': 'scorer', 'scores': {}})


def _use_provider(monkeypatch, provider):
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: provider)
    return provider


def test_the_llm_promotes_a_near_to_correct(client, attempt, near_verdict, monkeypatch):
    p = _use_provider(monkeypatch, _Provider(reply={'same': True}))

    body = _grade(client, attempt, 'CO2').json()

    assert (body['verdict'], body['how'], body['is_correct']) == ('correct', 'llm', True)
    assert len(p.calls) == 1
    assert '"CO2"' in p.calls[0]          # the typed answer travels as quoted data


def test_the_llm_demotes_a_near_to_wrong(client, attempt, near_verdict, monkeypatch):
    _use_provider(monkeypatch, _Provider(reply={'same': False}))
    body = _grade(client, attempt, 'a gas').json()
    assert (body['verdict'], body['how']) == ('wrong', 'llm')


def test_an_unavailable_llm_leaves_near_alone(client, attempt, near_verdict, monkeypatch):
    _use_provider(monkeypatch, _Provider(raise_=RuntimeError('ollama is down')))
    body = _grade(client, attempt, 'a gas').json()
    assert (body['verdict'], body['how']) == ('near', 'scorer')


def test_a_malformed_llm_reply_leaves_near_alone(client, attempt, near_verdict, monkeypatch):
    _use_provider(monkeypatch, _Provider(reply={'answer': 'yes'}))
    body = _grade(client, attempt, 'a gas').json()
    assert body['verdict'] == 'near'


def test_a_clear_verdict_never_reaches_the_llm(client, attempt, monkeypatch):
    p = _use_provider(monkeypatch, _Provider(raise_=AssertionError('must not be called')))
    assert _grade(client, attempt, 'carbon dioxide').json()['verdict'] == 'correct'
    assert _grade(client, attempt, 'oxygen').json()['verdict'] == 'wrong'
    assert p.calls == []


# ---- override ---------------------------------------------------------------------

def _override(client, attempt, answer_id, is_correct=True):
    return client.post(f'/api/quizzes/attempts/{attempt.id}/override_answer/',
                       {'answer_id': answer_id, 'is_correct': is_correct}, format='json')


def test_the_student_can_overrule_a_wrong_and_it_counts(client, attempt):
    answer_id = _grade(client, attempt, 'oxygen').json()['id']

    res = _override(client, attempt, answer_id)

    assert res.status_code == 200
    row = Answer.objects.get(id=answer_id)
    assert (row.is_correct, row.points_earned, row.overridden) == (True, 1, True)
    done = client.post(f'/api/quizzes/attempts/{attempt.id}/complete/', {}, format='json').json()
    assert done['score'] == 100.0


def test_a_choice_answer_cannot_be_overridden(client, attempt):
    q = attempt.quiz.questions.first()
    row = client.post(f'/api/quizzes/attempts/{attempt.id}/submit_answer/',
                      {'question_id': q.id, 'answer': 'oxygen'}, format='json').json()
    assert _override(client, attempt, row['id']).status_code == 400


def test_override_is_refused_once_the_attempt_is_completed(client, attempt):
    answer_id = _grade(client, attempt, 'oxygen').json()['id']
    QuizAttempt.objects.filter(id=attempt.id).update(is_completed=True)
    assert _override(client, attempt, answer_id).status_code == 400


def test_another_users_attempt_is_not_found(other_user, attempt):
    from rest_framework.test import APIClient
    theirs = APIClient(HTTP_HOST='localhost'); theirs.force_authenticate(other_user)
    assert _grade(theirs, attempt, 'carbon dioxide').status_code == 404
