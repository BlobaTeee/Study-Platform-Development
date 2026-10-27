"""Practice problems: apply a document to a case it does not spell out, solve
in steps, and be graded against a rubric written with the problem.

The model is scripted here; what is tested is everything around it: which
problems are kept, what the page may see, how a grade is read, when the
solution unlocks, and what Progress counts.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from exercises.models import Exercise, ExerciseAttempt
from exercises.services.grading import fallback_hint, leaks
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

CONTRACT = ('A contract is breached when a party fails to deliver on the agreed date. The party in breach must '
            'pay damages that put the other party where it would have been. Late delivery of more than fourteen '
            'days lets the buyer end the contract. ') * 5

Q1 = 'A contract is breached when a party fails to deliver on the agreed date'
Q2 = 'pay damages that put the other party where it would have been'
Q3 = 'Late delivery of more than fourteen days lets the buyer end the contract'


def problem(prompt, difficulty, quotes, solution=None):
    return {'prompt': prompt, 'difficulty': difficulty,
            'solution': solution or ['A delivered late, so A breached.', 'B may claim damages.'],
            'checkpoints': [{'text': f'Point {i}', 'basis': q} for i, q in enumerate(quotes, 1)],
            'mistakes': [{'text': 'Blames B', 'type': 'concept'}, {'text': 'Odd', 'type': 'nonsense'}]}


class Scripted:
    """Answers each request with the next reply in the script."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def model(monkeypatch):
    def use(*replies):
        provider = Scripted(*replies)
        monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: provider)
        return provider
    return use


@pytest.fixture
def contract(notebook):
    return make_source(notebook, 'Contracts', CONTRACT)


def _exercise(user, notebook, prompt='Company A delivered 20 days late. What can B do?', solution=None):
    return Exercise.objects.create(
        user=user, notebook=notebook, prompt=prompt,
        reference={'solution': solution or ['A delivered late, so A breached.', 'B may end the contract.'],
                   'checkpoints': [{'id': 1, 'text': 'A is in breach', 'basis': Q1},
                                   {'id': 2, 'text': 'B may end the contract', 'basis': Q3}],
                   'mistakes': []})


# ---- writing problems -----------------------------------------------------------------

def test_three_problems_come_from_a_document_easiest_first(client, model, contract):
    provider = model({'problems': [
        problem('Company A shipped 20 days late. Advise the buyer B on its options.', 'hard', [Q1, Q3]),
        problem('Company A missed the delivery date by a day. Is this a breach?', 'easy', [Q1, Q2]),
        problem('B lost a resale because A was late. What should A pay?', 'medium', [Q2, Q1]),
    ]})

    res = client.post('/api/exercises/generate/', {'source_id': contract.id}, format='json')

    assert res.status_code == 201
    assert [p['difficulty'] for p in res.json()['results']] == ['easy', 'medium', 'hard']
    assert 'reference' not in res.json()['results'][0]
    assert 'Never\na recall question' in provider.prompts[0]
    saved = Exercise.objects.get(prompt__startswith='Company A shipped')
    assert saved.source == contract and saved.origin == 'document'
    assert saved.reference['language'] == 'en'
    assert [m['type'] for m in saved.reference['mistakes']] == ['concept']   # unknown type dropped


def test_a_checkpoint_the_document_does_not_say_is_dropped(client, model, contract):
    model({'problems': [
        problem('Company A shipped 20 days late. Advise the buyer B on its options.', 'medium',
                [Q1, 'a penalty of ten percent applies to every late order', Q3]),
        problem('Company A missed a date. Explain what the seller now owes the buyer.', 'easy',
                [Q1, 'the seller always owes double the price of the goods']),
    ]})

    res = client.post('/api/exercises/generate/', {'source_id': contract.id}, format='json')

    kept = Exercise.objects.get()
    assert len(res.json()['results']) == 1       # the second kept only one grounded checkpoint
    assert [c['basis'] for c in kept.reference['checkpoints']] == [Q1, Q3]
    assert [c['id'] for c in kept.reference['checkpoints']] == [1, 2]


def test_nothing_usable_is_an_error_and_nothing_is_saved(client, model, contract):
    model({'problems': [problem('Too short', 'easy', [Q1, Q2])]})

    res = client.post('/api/exercises/generate/', {'source_id': contract.id}, format='json')

    assert res.status_code == 503
    assert not Exercise.objects.exists()


def test_a_quota_error_says_try_later(client, model, contract):
    model(RuntimeError('429 RESOURCE_EXHAUSTED quota'))

    res = client.post('/api/exercises/generate/', {'source_id': contract.id}, format='json')

    assert res.status_code == 503
    assert 'free requests' in res.json()['detail']


def test_someone_elses_document_is_refused(other_client, model, contract):
    model()
    res = other_client.post('/api/exercises/generate/', {'source_id': contract.id}, format='json')
    assert res.status_code == 404


def test_an_own_problem_that_misses_a_given_is_refused(client, model):
    model({'complete': False, 'missing': 'The problem does not say how late the delivery was.'})

    res = client.post('/api/exercises/own/', {'text': 'A delivered late. Can B end the contract?'}, format='json')

    assert res.status_code == 400
    assert res.json()['incomplete'] is True
    assert 'how late' in res.json()['detail']
    assert not Exercise.objects.exists()


def test_an_own_problem_gets_a_rubric_and_belongs_to_no_notebook(client, model, user, notebook):
    model({'complete': True, 'prompt': 'Solve 2x + 3 = 11 for x and check your answer.', 'difficulty': 'easy',
           'solution': ['2x = 8', 'x = 4'],
           'checkpoints': [{'text': 'Isolates 2x', 'basis': ''}, {'text': 'Finds x = 4', 'basis': ''}],
           'mistakes': [{'text': 'Adds 3 instead of subtracting', 'type': 'execution'}]})

    res = client.post('/api/exercises/own/', {'text': 'Solve 2x + 3 = 11 for x and check your answer.'},
                      format='json')

    assert res.status_code == 201
    body = res.json()
    assert body['origin'] == 'own' and body['checkpoint_count'] == 2
    assert body['notebook_id'] is None and body['notebook_title'] == ''
    assert body['solution'] is None              # hidden until solved
    _exercise(user, notebook)                    # a document problem, not listed with them
    own = client.get('/api/exercises/?own=1').json()['results']
    assert [e['id'] for e in own] == [body['id']]
    everything = client.get('/api/exercises/').json()['results']
    assert [(e['origin'], e['notebook_title']) for e in everything] == [('own', ''), ('document', 'Biology')]


# ---- grading -----------------------------------------------------------------------------

def test_reaching_every_checkpoint_first_time_is_mastered(client, model, user, notebook):
    ex = _exercise(user, notebook)
    model({'met': [1, 2], 'first_wrong_step': None, 'error_type': None, 'detail': '', 'hint': ''})

    res = client.post(f'/api/exercises/{ex.id}/submit/', {'steps': ['A is late, so in breach.', 'B can end it.']},
                      format='json')

    body = res.json()
    assert body['attempts'][-1]['result']['verdict'] == 'passed'
    assert body['status'] == 'mastered'
    assert body['solution'] == ['A delivered late, so A breached.', 'B may end the contract.']


def test_a_wrong_step_is_named_and_the_solution_stays_hidden(client, model, user, notebook):
    ex = _exercise(user, notebook)
    model({'met': [1, 9], 'first_wrong_step': 2, 'error_type': 'concept',
           'detail': 'Ending the contract needs more than fourteen days of delay.', 'hint': 'How late was A?'})

    res = client.post(f'/api/exercises/{ex.id}/submit/', {'steps': ['A is in breach.', 'B must wait a month.', '']},
                      format='json')

    body = res.json()
    result = body['attempts'][-1]['result']
    assert result == {'verdict': 'needs_work', 'met': [1], 'first_wrong_step': 2, 'error_type': 'concept',
                      'detail': 'Ending the contract needs more than fourteen days of delay.', 'hint': 'How late was A?',
                      'quote': '', 'quote_step': None}
    assert body['attempts'][-1]['steps'] == ['A is in breach.', 'B must wait a month.']   # blank step dropped
    assert body['solution'] is None
    assert [c['id'] for c in body['met_checkpoints']] == [1]
    listed = client.get(f'/api/exercises/?notebook={notebook.id}').json()['results']
    assert listed[0]['attempted'] is True and listed[0]['status'] == 'new'


def test_stopping_short_points_past_the_last_step(client, model, user, notebook):
    ex = _exercise(user, notebook)
    model({'met': [1], 'first_wrong_step': None, 'error_type': 'whatever', 'detail': 'Says nothing about B.'})

    res = client.post(f'/api/exercises/{ex.id}/submit/', {'steps': ['A is in breach.']}, format='json')

    result = res.json()['attempts'][-1]['result']
    assert result['verdict'] == 'needs_work'
    assert result['first_wrong_step'] == 2 and result['error_type'] == 'missing_step'


def test_a_hint_that_gives_the_solution_away_is_replaced(client, model, user, notebook):
    ex = _exercise(user, notebook)
    model({'hint': 'Remember that A delivered late, so A breached the contract.'})

    res = client.post(f'/api/exercises/{ex.id}/hint/', {'steps': []}, format='json')

    hint = res.json()['attempts'][-1]['result']['hint']
    assert hint == 'Does your answer establish this yet: A is in breach?'


def test_the_solution_unlocks_after_three_failed_submits(client, model, user, notebook):
    ex = _exercise(user, notebook)
    wrong = {'met': [], 'first_wrong_step': 1, 'error_type': 'misread', 'detail': 'x', 'hint': 'y'}
    model(wrong, wrong, wrong)

    assert client.post(f'/api/exercises/{ex.id}/reveal/').status_code == 400
    for _ in range(3):
        body = client.post(f'/api/exercises/{ex.id}/submit/', {'steps': ['B is in breach.']}, format='json').json()
    assert body['can_reveal'] is True

    body = client.post(f'/api/exercises/{ex.id}/reveal/').json()

    assert body['solution'] and body['status'] == 'revisit'
    assert body['revisit_on'] == str(timezone.localdate() + timedelta(days=3))


def test_a_revisit_that_falls_due_hides_the_solution_again(client, model, user, notebook):
    ex = _exercise(user, notebook)
    ExerciseAttempt.objects.create(exercise=ex, kind='reveal')
    Exercise.objects.filter(pk=ex.pk).update(status='revisit', revisit_on=timezone.localdate() - timedelta(days=1),
                                             round_started_at=timezone.now() - timedelta(days=4))

    body = client.get(f'/api/exercises/{ex.id}/').json()

    assert body['status'] == 'new' and body['solution'] is None and body['attempts'] == []


def test_passing_after_a_miss_comes_back_later(client, model, user, notebook):
    ex = _exercise(user, notebook)
    model({'met': [1], 'first_wrong_step': 2, 'error_type': 'concept', 'detail': 'x', 'hint': 'y'},
          {'met': [1, 2], 'first_wrong_step': None})

    client.post(f'/api/exercises/{ex.id}/submit/', {'steps': ['A is in breach.', 'B waits.']}, format='json')
    body = client.post(f'/api/exercises/{ex.id}/submit/', {'steps': ['A is in breach.', 'B ends it.']},
                       format='json').json()

    assert body['status'] == 'revisit' and body['solution']


def test_a_failed_grade_keeps_nothing_and_says_so(client, model, user, notebook):
    ex = _exercise(user, notebook)
    model(RuntimeError('timed out'))

    res = client.post(f'/api/exercises/{ex.id}/submit/', {'steps': ['A is in breach.']}, format='json')

    assert res.status_code == 503 and 'kept' in res.json()['detail']
    assert not ExerciseAttempt.objects.exists()


def test_someone_elses_problem_is_not_found(other_client, user, notebook):
    ex = _exercise(user, notebook)
    assert other_client.get(f'/api/exercises/{ex.id}/').status_code == 404
    assert other_client.post(f'/api/exercises/{ex.id}/submit/', {'steps': ['x']}, format='json').status_code == 404


# ---- what Progress counts ------------------------------------------------------------------

def test_mistakes_are_counted_by_type_per_notebook(client, user, notebook):
    ex = _exercise(user, notebook)
    for kind in ('concept', 'concept', 'execution'):
        ExerciseAttempt.objects.create(exercise=ex, kind='submit', steps=['x'],
                                       result={'verdict': 'needs_work', 'error_type': kind})
    ExerciseAttempt.objects.create(exercise=ex, kind='submit', steps=['x'], result={'verdict': 'passed'})

    body = client.get('/api/exercises/mistakes/').json()

    assert body['notebooks'] == [{'notebook_id': notebook.id, 'title': 'Biology', 'total': 3, 'types': [
        {'type': 'concept', 'count': 2, 'exercise_ids': [ex.id]},
        {'type': 'execution', 'count': 1, 'exercise_ids': [ex.id]}]}]


def test_own_problems_mistakes_share_a_line_of_their_own(client, user, notebook):
    own = Exercise.objects.create(user=user, notebook=None, origin='own', prompt='Solve 2x + 3 = 11.',
                                  reference={'solution': ['x = 4'], 'checkpoints': [], 'mistakes': []})
    ExerciseAttempt.objects.create(exercise=own, kind='submit', steps=['x'],
                                   result={'verdict': 'needs_work', 'error_type': 'execution'})

    body = client.get('/api/exercises/mistakes/').json()

    assert body['notebooks'] == [{'notebook_id': None, 'title': '', 'total': 1, 'types': [
        {'type': 'execution', 'count': 1, 'exercise_ids': [own.id]}]}]


# ---- the leak check, on its own -------------------------------------------------------------

def test_a_number_the_problem_never_gave_is_a_leak(user, notebook):
    ex = _exercise(user, notebook, prompt='Solve 2x + 3 = 11.', solution=['2x = 8', 'x = 4'])
    assert leaks('Is x equal to 4?', ex)
    assert not leaks('What do you get if you take 3 from both sides of 11?', ex)
    assert not leaks('', ex)


def test_the_fallback_hint_speaks_the_problems_language(user, notebook):
    ex = _exercise(user, notebook, prompt='Công ty A giao hàng trễ 20 ngày so với hợp đồng. Bên B có quyền gì?')
    assert fallback_hint(ex, [1]) == 'Bài làm của bạn đã có ý này chưa: B may end the contract?'


def test_the_wrong_step_is_found_by_its_quote_when_the_number_is_off(user, notebook):
    # Graders often name the right step in words and give its number off by
    # one; the quoted step is the one to trust.
    from exercises.services.grading import clean_grade
    ex = _exercise(user, notebook)
    steps = ['A and B had a contract.', 'A breached it by delivering late.', 'Damages are what A gained.']
    reply = {'met': [1], 'first_wrong_step': 2, 'wrong_step_quote': 'Damages are what A gained',
             'error_type': 'concept', 'detail': 'Damages compensate loss.', 'hint': 'What did B lose?'}
    graded = clean_grade(reply, ex, steps)
    assert graded['first_wrong_step'] == 3
    # Kept so an evaluation can tell a quote that matched from one that did not.
    assert graded['quote'] == 'Damages are what A gained' and graded['quote_step'] == 3


def test_a_quote_that_matches_no_step_leaves_the_number_alone(user, notebook):
    from exercises.services.grading import clean_grade
    ex = _exercise(user, notebook)
    steps = ['A and B had a contract.', 'A breached it.']
    reply = {'met': [1], 'first_wrong_step': 2, 'wrong_step_quote': 'something never written',
             'error_type': 'concept', 'detail': 'x', 'hint': 'y'}
    assert clean_grade(reply, ex, steps)['first_wrong_step'] == 2


def test_the_grader_is_told_a_right_step_before_a_wrong_one_is_not_the_wrong_step(model, user, notebook):
    # Measured on the hand-made set: graders pointed at the last right step
    # before the slip (econ-1/2 quoted "40 per year" for "40 x 3 = 160").
    from exercises.services.grading import grade
    provider = model({'met': [1, 2], 'first_wrong_step': None})
    grade(_exercise(user, notebook), ['A is in breach.', 'B may end it.'])
    prompt = provider.prompts[0]
    assert 'contains a mistake itself' in prompt
    assert 'a right step that is followed by a wrong one is not the wrong step' in prompt.lower()
