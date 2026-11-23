"""Mock tests in the shape of a real exam: parts of different answer kinds,
each marked by the exam's rules (docs/specs/2026-11-23-exam-format-mock-tests.md)."""
import json

import pytest

from exercises.models import Exercise
from quizzes.models import MockTest, MockTestQuestion, Question, Quiz, TrueFalseItem
from quizzes.services.exam import suits_typing, tf_earned, written_earned

pytestmark = pytest.mark.django_db
URL = '/api/quizzes/mock-tests/'
BASIS = 'Sentence number 3 explains a distinct idea'


def _bank(user, notebook, long=12, short=6):
    """Multiple-choice questions: `long` with a sentence for an answer (choice
    only) and `short` with a one-word answer (can be typed)."""
    quiz = Quiz.objects.create(user=user, title='Pool', is_published=True)
    quiz.sources.set(notebook.sources.all())
    for i in range(long):
        Question.objects.create(quiz=quiz, question_text=f'Long {i}?', question_type='multiple_choice',
                                options=['the first rather long answer here that goes on', 'b', 'c', 'd'],
                                correct_answer='the first rather long answer here that goes on', order=i)
    for i in range(short):
        Question.objects.create(quiz=quiz, question_text=f'Short {i}?', question_type='multiple_choice',
                                options=['mitochondria', 'ribosome', 'nucleus', 'golgi'],
                                correct_answer='mitochondria', order=100 + i)


def _tf_items(notebook, n=4):
    for i in range(n):
        TrueFalseItem.objects.create(notebook=notebook, stem=f'Stem {i}', statements=[
            {'label': 'a', 'text': 'A', 'answer': True, 'basis': BASIS},
            {'label': 'b', 'text': 'B', 'answer': False, 'basis': BASIS},
            {'label': 'c', 'text': 'C', 'answer': True, 'basis': BASIS},
            {'label': 'd', 'text': 'D', 'answer': False, 'basis': BASIS}])


class NoModel:
    """Fails the test if anything asks the model."""

    def generate_json(self, prompt):
        raise AssertionError('no model request expected')


@pytest.fixture
def no_model(monkeypatch):
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: NoModel())


# ---- the arithmetic ----------------------------------------------------------------------

def test_true_false_is_marked_like_the_thpt_exam():
    sts = [{'label': x, 'answer': a} for x, a in zip('abcd', [True, False, True, False])]
    assert tf_earned({'a': True, 'b': False, 'c': True, 'd': False}, sts, 1.0) == (1.0, 4)
    assert tf_earned({'a': True, 'b': False, 'c': True, 'd': True}, sts, 1.0) == (0.5, 3)
    assert tf_earned({'a': True, 'b': False}, sts, 1.0) == (0.25, 2)
    assert tf_earned({'a': True}, sts, 1.0) == (0.1, 1)
    assert tf_earned({}, sts, 1.0) == (0.0, 0)


def test_a_written_answer_earns_its_share_of_checkpoints():
    assert written_earned({'verdict': 'passed', 'met': [1]}, 3, 5.0) == 5.0
    assert written_earned({'verdict': 'needs_work', 'met': [1, 2]}, 4, 5.0) == 2.5
    assert written_earned({'verdict': 'needs_work', 'met': []}, 4, 5.0) == 0.0


def test_only_short_answers_are_typed():
    assert suits_typing('mitochondria') and suits_typing('the inner membrane')
    assert not suits_typing('the first rather long answer here that goes on')
    assert not suits_typing('')


# ---- a THPT-shaped sitting -----------------------------------------------------------------

def _thpt(client, notebook):
    res = client.post(URL, {'notebook': notebook.id, 'template': 'thpt'}, format='json')
    assert res.status_code == 201, res.json()
    return res.json()


def test_a_thpt_paper_has_its_three_parts_in_order_and_hides_answers(client, user, notebook, no_model):
    _bank(user, notebook)
    _tf_items(notebook)
    body = _thpt(client, notebook)

    assert body['template'] == 'thpt' and body['duration_minutes'] == 90
    sections = [q['section'] for q in body['paper']]
    assert sections == ['choice'] * 12 + ['true_false'] * 4 + ['short'] * 6
    shorts = [q for q in body['paper'] if q['section'] == 'short']
    assert all(q['options'] == [] and q['question_text'].startswith('Short') for q in shorts)
    tf = next(q for q in body['paper'] if q['section'] == 'true_false')
    assert [st['label'] for st in tf['statements']] == ['a', 'b', 'c', 'd']
    assert 'answer' not in json.dumps(tf['statements'])
    assert 'short_paper' not in body


def test_a_thpt_paper_is_marked_part_by_part_out_of_ten(client, user, notebook, no_model):
    _bank(user, notebook)
    _tf_items(notebook)
    body = _thpt(client, notebook)
    answer = lambda q, a: client.post(f"{URL}{body['id']}/answer/", {'paper_question_id': q['id'], 'answer': a},
                                      format='json')
    for q in body['paper']:
        if q['section'] == 'choice':
            answer(q, 'the first rather long answer here that goes on')          # all 12 right: 3 points
        elif q['section'] == 'true_false':
            answer(q, {'a': True, 'b': False, 'c': True, 'd': True})  # 3 of 4 each: 4 x 0.5 = 2
        else:
            answer(q, 'Mitochondria')                                # 6 typed right: 3 points
    res = client.post(f"{URL}{body['id']}/submit/").json()

    parts = {p['section']: p for p in res['parts']}
    assert (parts['choice']['earned'], parts['choice']['points']) == (3.0, 3.0)
    assert (parts['true_false']['earned'], parts['true_false']['points']) == (2.0, 4.0)
    assert (parts['short']['earned'], parts['short']['points']) == (3.0, 3.0)
    assert res['score'] == 80.0                                       # 8 of 10
    tf = next(q for q in res['paper'] if q['section'] == 'true_false')
    assert tf['statements'][0]['answer'] is True                      # revealed after submit


def test_too_few_true_false_items_are_written_and_kept(client, user, notebook, monkeypatch):
    from notebooks.models import Source
    src = Source.objects.filter(notebook=notebook).first()

    class Writer:
        prompts = []

        def generate_json(self, prompt):
            self.prompts.append(prompt)
            return {'questions': [{'document': src.id, 'stem': f'Stem {i}', 'statements': [
                {'label': x, 'text': f'Statement {x}', 'answer': x in 'ac', 'basis': BASIS} for x in 'abcd']}
                for i in range(6)]}

    writer = Writer()
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: writer)
    _bank(user, notebook)

    body = _thpt(client, notebook)

    assert len(writer.prompts) == 1
    assert TrueFalseItem.objects.filter(notebook=notebook).count() == 6
    assert sum(1 for q in body['paper'] if q['section'] == 'true_false') == 4
    assert body['generated_questions'] is True


def test_a_true_false_item_whose_statement_quotes_nothing_is_dropped(client, user, notebook, monkeypatch):
    class Writer:
        def generate_json(self, prompt):
            return {'questions': [{'stem': 'Stem', 'statements': [
                {'label': x, 'text': 'S', 'answer': x == 'a', 'basis': 'words that are nowhere in the text'}
                for x in 'abcd']}]}

    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: Writer())
    _bank(user, notebook)
    body = _thpt(client, notebook)
    assert not TrueFalseItem.objects.exists()
    assert body['short_paper'] is True and body['missing_parts'] == ['true_false']


def test_a_notebook_with_few_short_answers_gets_a_shorter_part_three(client, user, notebook, no_model):
    _bank(user, notebook, long=14, short=2)
    _tf_items(notebook)
    body = _thpt(client, notebook)
    assert sum(1 for q in body['paper'] if q['section'] == 'short') == 2
    assert body['missing_parts'] == ['short']


# ---- a 45-minute test with a written problem -----------------------------------------------

def test_a_45_minute_test_grades_its_written_problem_by_checkpoints(client, user, notebook, monkeypatch):
    _bank(user, notebook)
    _tf_items(notebook, n=2)
    Exercise.objects.create(user=user, notebook=notebook, prompt='Explain why cells divide in two stages.',
                            reference={'solution': ['Step one.', 'Step two.'], 'language': 'en',
                                       'checkpoints': [{'id': 1, 'text': 'A', 'basis': ''},
                                                       {'id': 2, 'text': 'B', 'basis': ''}], 'mistakes': []})

    class Grader:
        def generate_json(self, prompt):
            return {'met': [1], 'first_wrong_step': 2, 'wrong_step_quote': '', 'error_type': 'concept',
                    'detail': 'Second stage is wrong.', 'hint': 'What happens next?'}

    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: Grader())
    body = client.post(URL, {'notebook': notebook.id, 'template': 'test45'}, format='json').json()
    assert [q['section'] for q in body['paper']][-1] == 'written' and body['duration_minutes'] == 45
    written = body['paper'][-1]
    client.post(f"{URL}{body['id']}/answer/", {'paper_question_id': written['id'],
                                               'answer': 'Cells copy their DNA. Then they split once.'},
                format='json')

    res = client.post(f"{URL}{body['id']}/submit/").json()

    row = res['paper'][-1]
    assert row['earned'] == 2.5 and row['points'] == 5.0
    assert row['solution'] == ['Step one.', 'Step two.']
    assert row['grade']['detail'] == 'Second stage is wrong.'


def test_a_written_answer_the_model_cannot_mark_earns_nothing_but_the_paper_is_submitted(
        client, user, notebook, monkeypatch):
    _bank(user, notebook)
    _tf_items(notebook, n=2)
    Exercise.objects.create(user=user, notebook=notebook, prompt='Explain why cells divide in two stages.',
                            reference={'solution': ['x'], 'checkpoints': [{'id': 1, 'text': 'A', 'basis': ''},
                                                                          {'id': 2, 'text': 'B', 'basis': ''}]})

    class Down:
        def generate_json(self, prompt):
            raise RuntimeError('429 RESOURCE_EXHAUSTED quota')

    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: Down())
    body = client.post(URL, {'notebook': notebook.id, 'template': 'test45'}, format='json').json()
    written = body['paper'][-1]
    client.post(f"{URL}{body['id']}/answer/", {'paper_question_id': written['id'], 'answer': 'Some answer.'},
                format='json')

    res = client.post(f"{URL}{body['id']}/submit/").json()

    assert MockTest.objects.get(id=body['id']).completed_at is not None
    assert res['paper'][-1]['grade'] == {'not_graded': True} and res['paper'][-1]['earned'] == 0.0



def test_a_written_answer_is_marked_on_the_normal_lane_and_tried_twice(client, user, notebook, monkeypatch):
    """Marked once, at submit: a slow or failed first reply must not cost the part's points."""
    from notebooks.services.model_lane import is_quick

    _bank(user, notebook)
    _tf_items(notebook, n=2)
    Exercise.objects.create(user=user, notebook=notebook, prompt='Explain why cells divide in two stages.',
                            reference={'solution': ['x'], 'language': 'en',
                                       'checkpoints': [{'id': 1, 'text': 'A', 'basis': ''},
                                                       {'id': 2, 'text': 'B', 'basis': ''}], 'mistakes': []})
    lanes = []

    class SlowThenFine:
        def generate_json(self, prompt):
            lanes.append(is_quick())
            if len(lanes) == 1:
                raise RuntimeError('429 RESOURCE_EXHAUSTED quota')
            return {'met': [1, 2], 'first_wrong_step': None, 'wrong_step_quote': '', 'error_type': '',
                    'detail': '', 'hint': ''}

    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: SlowThenFine())
    body = client.post(URL, {'notebook': notebook.id, 'template': 'test45'}, format='json').json()
    written = body['paper'][-1]
    client.post(f"{URL}{body['id']}/answer/", {'paper_question_id': written['id'],
                                               'answer': 'Cells copy their DNA. Then they split twice.'},
                format='json')

    res = client.post(f"{URL}{body['id']}/submit/").json()

    assert lanes == [False, False]
    assert res['paper'][-1]['earned'] == 5.0 and 'not_graded' not in res['paper'][-1]['grade']

# ---- what stays as it was ------------------------------------------------------------------

def test_a_paper_without_a_template_is_still_the_classic_one(client, user, notebook, no_model):
    _bank(user, notebook, long=5, short=0)
    body = client.post(URL, {'notebook': notebook.id, 'question_count': 5, 'duration_minutes': 10},
                       format='json').json()
    assert body['template'] == '' and {q['section'] for q in body['paper']} == {'choice'}


def test_an_unknown_template_is_refused(client, user, notebook):
    res = client.post(URL, {'notebook': notebook.id, 'template': 'nope'}, format='json')
    assert res.status_code == 400


def test_true_false_and_written_rows_stay_out_of_the_mistake_bank(client, user, notebook, no_model):
    _bank(user, notebook)
    _tf_items(notebook)
    body = _thpt(client, notebook)
    res = client.post(f"{URL}{body['id']}/submit/").json()    # nothing answered: everything wrong
    # 12 choice + 6 short questions are owed; the 4 true/false items are not questions.
    assert res['mistake_count'] == 18
    assert MockTestQuestion.objects.filter(mock_test_id=body['id'], question__isnull=True).count() == 4


# ---- a mixed paper: a new shape every sitting --------------------------------------------

def test_a_mixed_shape_is_always_worth_ten_points_and_varies():
    import random
    from quizzes.services.exam import mixed_parts
    shapes = set()
    for seed in range(200):
        shape = mixed_parts(random.Random(seed))
        parts = {kind: (n, pts) for kind, n, pts in shape['parts']}
        assert sum(n * pts for n, pts in parts.values()) == 10
        assert parts['choice'][0] in (8, 12) and 2 <= parts['true_false'][0] <= 4
        assert parts['short'][0] <= 6 and parts['short'][1] == 0.5
        assert 20 <= shape['duration'] <= 120 and shape['duration'] % 5 == 0
        shapes.add(tuple(shape['parts']))
    assert len(shapes) > 5
    assert any('written' in {k for k, _, _ in s} for s in shapes)
    assert any('written' not in {k for k, _, _ in s} for s in shapes)


def test_a_mixed_sitting_freezes_one_shape_and_its_time(client, user, notebook, no_model, monkeypatch):
    _bank(user, notebook)
    _tf_items(notebook)
    shape = {'duration': 55, 'parts': [('choice', 8, 0.25), ('true_false', 3, 1.0), ('short', 6, 0.5),
                                       ('written', 1, 2.0)]}
    calls = []
    monkeypatch.setattr('quizzes.services.exam.mixed_parts', lambda: calls.append(1) or shape)
    Exercise.objects.create(user=user, notebook=notebook, prompt='Explain why cells divide in two stages.',
                            reference={'solution': ['x'], 'checkpoints': [{'id': 1, 'text': 'A', 'basis': ''}]})

    body = client.post(URL, {'notebook': notebook.id, 'template': 'mixed'}, format='json').json()

    assert len(calls) == 1                                  # drawn once, not once per use
    assert body['template'] == 'mixed' and body['duration_minutes'] == 55
    assert [q['section'] for q in body['paper']] == ['choice'] * 8 + ['true_false'] * 3 + ['short'] * 6 + ['written']
    assert sum(q['points'] for q in body['paper']) == 10
