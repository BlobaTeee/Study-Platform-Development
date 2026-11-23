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

    def generate_json_from_images(self, prompt, images):
        self.images = images
        return self.generate_json(prompt)


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
    assert 'Never a recall question' in provider.prompts[0]
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


def test_deleting_a_problem_takes_its_attempts_and_mistakes_with_it(client, user, notebook):
    from exercises.models import ExerciseAttempt
    ex = _exercise(user, notebook)
    ExerciseAttempt.objects.create(exercise=ex, kind='submit', steps=['x'],
                                   result={'verdict': 'needs_work', 'error_type': 'concept'})
    assert client.get('/api/exercises/mistakes/').json()['notebooks']

    assert client.delete(f'/api/exercises/{ex.id}/').status_code == 204

    assert not Exercise.objects.filter(id=ex.id).exists()
    assert not ExerciseAttempt.objects.filter(exercise_id=ex.id).exists()
    assert client.get('/api/exercises/mistakes/').json()['notebooks'] == []


def test_someone_elses_problem_cannot_be_deleted(other_client, user, notebook):
    ex = _exercise(user, notebook)
    assert other_client.delete(f'/api/exercises/{ex.id}/').status_code == 404
    assert Exercise.objects.filter(id=ex.id).exists()


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


# ---- answer format: steps or points, by subject ----------------------------------------

def test_problems_are_asked_to_suit_the_subject_and_vary_in_kind(client, model, contract):
    provider = model({'problems': [
        problem('Company A shipped 20 days late. Advise the buyer B on its options.', 'hard', [Q1, Q3]),
    ]})
    client.post('/api/exercises/generate/', {'source_id': contract.id}, format='json')
    prompt = provider.prompts[0]
    assert 'which subject the material belongs to' in prompt
    assert 'geography' in prompt and 'technology' in prompt
    assert 'Do not make all three problems calculations' in prompt
    assert '"format": "steps|points"' in prompt


def test_a_points_problem_keeps_its_format_and_the_page_is_told(client, model, contract):
    model({'problems': [
        {**problem('Explain why B may end the contract when A is twenty days late.', 'medium', [Q1, Q3]),
         'format': 'points'},
        {**problem('Company A missed the date by a day. Is this a breach?', 'easy', [Q1, Q2]), 'format': 'odd'},
        problem('B lost a resale because A was late. What should A pay?', 'hard', [Q2, Q1]),
    ]})

    res = client.post('/api/exercises/generate/', {'source_id': contract.id}, format='json')

    assert res.status_code == 201
    formats = {e.prompt[:12]: e.reference['format'] for e in Exercise.objects.all()}
    assert formats == {'Explain why ': 'points', 'Company A mi': 'steps', 'B lost a res': 'steps'}
    points = Exercise.objects.get(prompt__startswith='Explain why')
    assert client.get(f'/api/exercises/{points.id}/').json()['answer_format'] == 'points'


def test_a_problem_saved_before_formats_reads_as_steps(client, user, notebook):
    ex = _exercise(user, notebook)                          # its reference has no "format"
    assert client.get(f'/api/exercises/{ex.id}/').json()['answer_format'] == 'steps'


def test_the_grader_reads_a_points_answer_as_points(model, user, notebook):
    from exercises.services.grading import grade
    ex = _exercise(user, notebook)
    ex.reference = {**ex.reference, 'format': 'points'}
    ex.save()
    provider = model({'met': [1, 2], 'first_wrong_step': None})
    grade(ex, ['A is in breach.', 'B may end it.'])
    prompt = provider.prompts[0]
    assert 'Sentence 1: A is in breach.' in prompt and 'Sentence 2: B may end it.' in prompt
    assert 'give the number of the sentence' in prompt
    assert 'separate reasons or arguments' in prompt


def test_a_steps_answer_is_numbered_by_sentence_too(model, user, notebook):
    from exercises.services.grading import grade
    provider = model({'met': [1, 2], 'first_wrong_step': None})
    grade(_exercise(user, notebook), ['A is in breach.', 'B may end it.'])
    prompt = provider.prompts[0]
    assert 'Sentence 1: A is in breach.' in prompt and 'separate reasons or arguments' not in prompt


# ---- free text: the answer as written, cut into sentences ------------------------------

def test_sentences_end_at_a_stop_followed_by_a_space():
    from exercises.services.common import split_sentences
    text = ('TP.HCM mưa từ tháng 5 đến 10 vì gió mùa tây nam. Còn Huế mưa muộn hơn! '
            'Vì sao? 2 nơi khác nhau.')
    assert split_sentences(text) == ['TP.HCM mưa từ tháng 5 đến 10 vì gió mùa tây nam.', 'Còn Huế mưa muộn hơn!',
                                     'Vì sao?', '2 nơi khác nhau.']


def test_a_sentence_without_a_capital_still_starts_a_new_one():
    from exercises.services.common import split_sentences
    assert split_sentences('tp.hcm mưa vì gió tây nam. còn huế mưa do núi. vậy hai nơi lệch nhau') == \
        ['tp.hcm mưa vì gió tây nam.', 'còn huế mưa do núi.', 'vậy hai nơi lệch nhau']


def test_decimals_short_forms_and_initials_do_not_end_a_sentence():
    from exercises.services.common import split_sentences
    assert split_sentences('Bể dài 1.5 m và rộng 1,5 m. Thể tích là 3.14 m³.') == \
        ['Bể dài 1.5 m và rộng 1,5 m.', 'Thể tích là 3.14 m³.']
    assert split_sentences('Có nhiều nguyên nhân: gió, núi, v.v. nên mưa lệch nhau.') == \
        ['Có nhiều nguyên nhân: gió, núi, v.v. nên mưa lệch nhau.']
    assert split_sentences('VD. một xưởng lắp quạt. Đến TP. Hồ Chí Minh vào tháng 5. Mưa nhiều.') == \
        ['VD. một xưởng lắp quạt.', 'Đến TP. Hồ Chí Minh vào tháng 5.', 'Mưa nhiều.']
    assert split_sentences('He met Dr. Smith and J. Lee. She agreed.') == ['He met Dr. Smith and J. Lee.', 'She agreed.']


def test_new_lines_list_markers_and_formulas():
    from exercises.services.common import split_sentences
    text = '2x + 3 = 11\n2x = 8\n\n   x = 4\n1. Tính thể tích. 2. Đổi ra lít.'
    assert split_sentences(text) == ['2x + 3 = 11', '2x = 8', 'x = 4', '1. Tính thể tích.', '2. Đổi ra lít.']
    assert split_sentences('') == [] and split_sentences(' \n ') == []


def test_a_very_long_answer_keeps_its_tail_in_the_last_sentence():
    from exercises.services.common import MAX_STEPS, split_sentences
    parts = split_sentences(' '.join(f'Câu số {i} đây.' for i in range(1, 51)))
    assert len(parts) == MAX_STEPS
    assert parts[-1].startswith(f'Câu số {MAX_STEPS} đây.') and parts[-1].endswith('Câu số 50 đây.')


def test_a_free_text_answer_is_graded_by_sentence_and_given_back_as_written(client, model, user, notebook):
    ex = _exercise(user, notebook)
    provider = model({'met': [1], 'first_wrong_step': 2, 'wrong_step_quote': 'B must wait a month.',
                      'error_type': 'concept', 'detail': 'Fourteen days is enough.', 'hint': 'How late was A?'})
    written = 'A is in breach. B must wait a month.\nThat is all.'

    res = client.post(f'/api/exercises/{ex.id}/submit/', {'text': written}, format='json')

    assert res.status_code == 201
    attempt = res.json()['attempts'][-1]
    assert attempt['steps'] == ['A is in breach.', 'B must wait a month.', 'That is all.']
    assert attempt['result']['first_wrong_step'] == 2 and attempt['result']['quote_step'] == 2
    assert attempt['result']['text'] == written
    assert 'Sentence 3: That is all.' in provider.prompts[0]


def test_a_hint_keeps_the_answer_as_written(client, model, user, notebook):
    ex = _exercise(user, notebook)
    model({'hint': 'How late was A?'})
    res = client.post(f'/api/exercises/{ex.id}/hint/', {'text': 'A is late. '}, format='json')
    attempt = res.json()['attempts'][-1]
    assert attempt['result'] == {'hint': 'How late was A?', 'text': 'A is late.'}
    assert attempt['steps'] == ['A is late.']


def test_an_empty_answer_is_refused(client, user, notebook):
    ex = _exercise(user, notebook)
    res = client.post(f'/api/exercises/{ex.id}/submit/', {'text': '  \n '}, format='json')
    assert res.status_code == 400


def test_the_grader_is_told_a_true_but_unneeded_sentence_is_not_a_mistake(model, user, notebook):
    # Seen with free text: all three checkpoints met, yet a true side remark
    # ("the highlands are higher, so colder") was flagged and the answer failed.
    from exercises.services.grading import grade
    provider = model({'met': [1, 2], 'first_wrong_step': None})
    grade(_exercise(user, notebook), ['A is in breach.', 'B may end it.', 'Contracts are old.'])
    assert 'true but not needed' in provider.prompts[0]


# ---- answer kinds: choice, true/false, short ---------------------------------------------

CHOICE_TEXT = ('Chọn một phương án đúng.\nMột vật rơi tự do từ độ cao 20 m, lấy g = 10 m/s². Thời gian rơi là\n'
               'A. 1 s   B. 2 s   C. 4 s   D. 20 s')
TF_TEXT = ('Chọn đúng hoặc sai cho mỗi ý.\nCho hàm số $f(x) = x^2 - 4x$.\n'
           'a) $f(0) = 0$\nb) Hàm số đồng biến trên $(2; +\\infty)$\nc) $f(4) = 4$')
SHORT_TEXT = 'Trả lời ngắn.\nMột hình chữ nhật dài 2,5 m và rộng 2 m. Diện tích bằng bao nhiêu mét vuông?'
RUBRIC = {'difficulty': 'easy', 'solution': ['Dùng công thức.', 'Ra kết quả.'],
          'checkpoints': [{'text': 'Dùng đúng công thức', 'basis': ''}, {'text': 'Ra đúng kết quả', 'basis': ''}],
          'mistakes': []}


def _own(client, model, text, reply):
    model({'complete': True, **RUBRIC, **reply})
    res = client.post('/api/exercises/own/', {'text': text}, format='json')
    assert res.status_code == 201, res.json()
    return res.json()


def _choice(client, model):
    return _own(client, model, CHOICE_TEXT, {
        'kind': 'choice', 'prompt': 'Một vật rơi tự do từ độ cao 20 m, lấy g = 10 m/s². Thời gian rơi là',
        'options': [{'label': 'A', 'text': '1 s'}, {'label': 'B', 'text': '2 s'},
                    {'label': 'C', 'text': '4 s'}, {'label': 'D', 'text': '20 s'}], 'answer': 'B'})


def test_a_choice_problem_shows_its_options_but_not_the_answer(client, model):
    body = _choice(client, model)
    assert body['answer_kind'] == 'choice'
    assert [o['label'] for o in body['options']] == ['A', 'B', 'C', 'D']
    assert 'A. 1 s' not in body['prompt']
    assert body['answer_key'] is None and 'answer' not in str(body['options'])


def test_a_choice_is_checked_without_the_model_and_a_first_right_pick_is_mastered(client, model):
    body = _choice(client, model)
    provider = model()                                   # any request would fail: the script is empty
    wrong = client.post(f"/api/exercises/{body['id']}/submit/", {'answer': 'C'}, format='json').json()
    assert wrong['attempts'][-1]['result']['verdict'] == 'needs_work'
    assert wrong['attempts'][-1]['result']['error_type'] == 'wrong_answer'
    right = client.post(f"/api/exercises/{body['id']}/submit/", {'answer': 'B'}, format='json').json()
    assert right['attempts'][-1]['result']['verdict'] == 'passed'
    assert right['status'] == 'revisit'                  # not first try
    assert right['answer_key'] == {'answer': 'B'}
    assert provider.prompts == []


def test_a_choice_that_is_not_an_option_is_refused(client, model):
    body = _choice(client, model)
    res = client.post(f"/api/exercises/{body['id']}/submit/", {'answer': 'E'}, format='json')
    assert res.status_code == 400


def test_options_the_problem_does_not_contain_fall_back_to_a_written_answer(client, model):
    body = _own(client, model, CHOICE_TEXT, {
        'kind': 'choice', 'prompt': 'Thời gian rơi là',
        'options': [{'label': 'A', 'text': '3 s'}, {'label': 'B', 'text': '2 s'}], 'answer': 'B'})
    assert body['answer_kind'] == 'written'
    assert 'A. 1 s' in body['prompt'] and body['options'] == []


def test_true_false_needs_every_statement_and_says_how_many_were_right(client, model):
    body = _own(client, model, TF_TEXT, {
        'kind': 'true_false', 'prompt': 'Cho hàm số $f(x) = x^2 - 4x$.',
        'statements': [{'label': 'a', 'text': '$f(0) = 0$', 'answer': True},
                       {'label': 'b', 'text': 'Hàm số đồng biến trên $(2; +\\infty)$', 'answer': True},
                       {'label': 'c', 'text': '$f(4) = 4$', 'answer': False}]})
    assert [st['label'] for st in body['statements']] == ['a', 'b', 'c']
    assert 'answer' not in body['statements'][0]
    url = f"/api/exercises/{body['id']}/submit/"
    assert client.post(url, {'answer': {'a': True}}, format='json').status_code == 400
    res = client.post(url, {'answer': {'a': True, 'b': False, 'c': False}}, format='json').json()
    result = res['attempts'][-1]['result']
    assert (result['verdict'], result['correct'], result['total']) == ('needs_work', 2, 3)


def test_a_short_answer_matches_by_value(client, model):
    body = _own(client, model, SHORT_TEXT, {
        'kind': 'short', 'prompt': 'Một hình chữ nhật dài 2,5 m và rộng 2 m. Diện tích bằng bao nhiêu mét vuông?',
        'answer': '5', 'accept': ['5 m²']})
    assert body['answer_kind'] == 'short'
    res = client.post(f"/api/exercises/{body['id']}/submit/", {'text': '5,0'}, format='json').json()
    assert res['attempts'][-1]['result']['verdict'] == 'passed'
    assert res['status'] == 'mastered'
    assert res['answer_key'] == {'answer': '5'}


def test_short_answers_compare_numbers_by_value_and_words_loosely():
    from exercises.services.grading import short_matches
    assert short_matches('12,5', ['12.5'])
    assert short_matches(' 12.50 ', ['12,5'])
    assert short_matches('$-3$', ['-3'])
    assert short_matches('Hà Nội.', ['hà nội'])
    assert not short_matches('12', ['12.5'])
    assert not short_matches('', ['0'])


def test_a_document_problem_stays_written(client, model, contract):
    model({'problems': [problem('Company A shipped 20 days late. Advise the buyer B on its options.', 'hard', [Q1, Q3])]})
    body = client.post('/api/exercises/generate/', {'source_id': contract.id}, format='json').json()
    ex = Exercise.objects.get(id=body['results'][0]['id'])
    assert client.get(f'/api/exercises/{ex.id}/').json()['answer_kind'] == 'written'


# ---- a set picked from one photo or file ---------------------------------------------------

def _keyed_choice():
    return {'complete': True, **RUBRIC, 'kind': 'choice',
            'prompt': 'Một vật rơi tự do từ độ cao 20 m, lấy g = 10 m/s². Thời gian rơi là',
            'options': [{'label': 'A', 'text': '1 s'}, {'label': 'B', 'text': '2 s'},
                        {'label': 'C', 'text': '4 s'}, {'label': 'D', 'text': '20 s'}], 'answer': 'B'}


def test_a_set_is_made_in_one_request_skips_what_is_missing_and_keeps_its_order(client, model):
    provider = model({'problems': [
        _keyed_choice(),
        {'complete': False, 'missing': 'Đề không cho chiều cao.'},
        {'complete': True, **RUBRIC, 'kind': 'written', 'prompt': 'Giải thích vì sao mùa mưa ở Huế lệch với TP.HCM.'},
    ]})
    texts = [CHOICE_TEXT, 'Tính thể tích bể nước hình hộp.', 'Giải thích vì sao mùa mưa ở Huế lệch với TP.HCM.']

    res = client.post('/api/exercises/own-set/', {'texts': texts}, format='json')

    assert res.status_code == 201
    body = res.json()
    assert len(provider.prompts) == 1
    assert [e['prompt'][:10] for e in body['results']] == ['Một vật rơ', 'Giải thích']
    assert body['skipped'] == [{'index': 1, 'reason': 'Đề không cho chiều cao.'}]
    first, second = (client.get(f"/api/exercises/{e['id']}/").json() for e in body['results'])
    assert first['answer_kind'] == 'choice' and second['answer_kind'] == 'written'
    assert first['set'] == {'index': 1, 'total': 2, 'prev_id': None, 'next_id': second['id']}
    assert first['set_title'] == '' and first['set_key'] == second['set_key'] != ''
    assert second['set']['prev_id'] == first['id'] and second['set']['next_id'] is None


def test_a_set_goes_three_problems_per_request(client, model):
    """Five answer keys in one reply ran past the deadline; three per request
    keep each reply short, and the requests run side by side."""
    one = {'complete': True, **RUBRIC, 'kind': 'written', 'prompt': 'Giải thích vì sao mùa mưa ở Huế lệch với TP.HCM.'}
    # The requests run in parallel, so any reply may answer any of them.
    provider = model(*[{'problems': [one] * 3}] * 3)
    texts = ['Giải thích vì sao mùa mưa ở Huế lệch với TP.HCM.'] * 7

    body = client.post('/api/exercises/own-set/', {'texts': texts}, format='json').json()

    assert len(provider.prompts) == 3
    assert len(body['results']) == 7 and body['skipped'] == []


def test_a_set_sends_its_cut_figures_along_as_pictures(client, model):
    """A description like "open-chain formula of a carbohydrate" does not say
    which one; the model reads the figure itself."""
    import base64, io
    from PIL import Image
    out = io.BytesIO()
    Image.new('RGB', (40, 20), 'white').save(out, 'PNG')
    picture = 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()
    one = {'complete': True, **RUBRIC, 'kind': 'written', 'prompt': 'Gọi tên chất [Figure 1: công thức mạch hở].'}
    provider = model({'problems': [one, one]})
    texts = ['Giải thích vì sao trời mưa vào mùa hè.', 'Gọi tên chất [Figure 1: công thức mạch hở].']

    res = client.post('/api/exercises/own-set/', {'texts': texts, 'figures': [[], [picture]]}, format='json')

    assert res.status_code == 201
    assert len(provider.images) == 1 and provider.images[0][1] == 'image/png'
    assert "picture 1 is Problem 2's Figure 1" in provider.prompts[0]
    assert 'never makes a problem incomplete' in provider.prompts[0]


def test_set_answer_keys_get_the_long_deadline_but_keep_thinking(client, model, monkeypatch):
    from notebooks.services import model_lane
    seen = []
    one = {'complete': True, **RUBRIC, 'kind': 'written', 'prompt': 'Giải thích vì sao mùa mưa ở Huế lệch với TP.HCM.'}
    provider = model({'problems': [one]})
    original = provider.generate_json

    def spy(prompt):
        seen.append((model_lane.is_long(), model_lane.thinks_less()))
        return original(prompt)
    monkeypatch.setattr(provider, 'generate_json', spy)
    client.post('/api/exercises/own-set/', {'texts': ['Giải thích vì sao mùa mưa ở Huế lệch với TP.HCM.']}, format='json')
    assert seen == [(True, False)]


def test_a_set_has_at_most_twenty_problems(client, model):
    res = client.post('/api/exercises/own-set/', {'texts': ['Giải thích vì sao trời mưa vào mùa hè.'] * 21}, format='json')
    assert res.status_code == 400


def test_a_set_where_nothing_could_be_made_is_an_error_and_saves_nothing(client, model):
    model({'problems': [{'complete': False, 'missing': 'Thiếu số liệu.'}]})
    res = client.post('/api/exercises/own-set/', {'texts': ['Tính thể tích bể nước hình hộp.']}, format='json')
    assert res.status_code == 400
    assert res.json() == {'detail': 'Thiếu số liệu.', 'incomplete': True}
    assert not Exercise.objects.exists()


def test_a_set_the_model_could_not_be_asked_about_is_503(client, model):
    from notebooks.services.gemini_client import GeminiQuotaError
    model(GeminiQuotaError('quota'))
    res = client.post('/api/exercises/own-set/', {'texts': ['Tính thể tích bể nước hình hộp.']}, format='json')
    assert res.status_code == 503


def test_a_problem_made_alone_has_no_set(client, user, notebook):
    ex = _exercise(user, notebook)
    assert client.get(f'/api/exercises/{ex.id}/').json()['set'] is None


def test_a_set_is_named_after_its_file_and_listed_as_one(client, model):
    one = {'complete': True, **RUBRIC, 'kind': 'written', 'prompt': 'Giải thích vì sao mùa mưa ở Huế lệch với TP.HCM.'}
    model({'problems': [one, one]})
    texts = ['Giải thích vì sao mùa mưa ở Huế lệch với TP.HCM.'] * 2
    client.post('/api/exercises/own-set/', {'texts': texts, 'title': '  Đề ôn tập Hoá 12  '}, format='json')

    listed = client.get('/api/exercises/').json()['results']
    assert {e['set_title'] for e in listed} == {'Đề ôn tập Hoá 12'}
    assert len({e['set_key'] for e in listed}) == 1


def test_a_set_can_be_renamed_only_by_its_owner(client, user, model):
    from django.contrib.auth import get_user_model
    ex = Exercise.objects.create(user=user, origin='own', set_key='k1', set_title='old', prompt='p', reference={})
    res = client.patch('/api/exercises/sets/k1/', {'title': '  Đề thi thử Hoá  '}, format='json')
    assert res.status_code == 200
    ex.refresh_from_db()
    assert ex.set_title == 'Đề thi thử Hoá'

    other = get_user_model().objects.create(username='someone-else')
    Exercise.objects.create(user=other, origin='own', set_key='k2', prompt='p', reference={})
    assert client.patch('/api/exercises/sets/k2/', {'title': 'x'}, format='json').status_code == 404


def test_a_set_reply_sent_as_a_bare_list_still_makes_the_set(client, model):
    one = {'complete': True, **RUBRIC, 'kind': 'written', 'prompt': 'Giải thích vì sao mùa mưa ở Huế lệch với TP.HCM.'}
    model([one, one])
    body = client.post('/api/exercises/own-set/', {'texts': ['Giải thích vì sao mùa mưa ở Huế lệch với TP.HCM.'] * 2},
                       format='json').json()
    assert len(body['results']) == 2
