"""A real paper added to practice, sat as that paper (2026-11-25).

The set's problems become a timed mock test: no hints, marked at the end out
of 10, part by part, against the paper's own answers. What is missed comes
back to practice, due today.
"""
import pytest
from django.utils import timezone

from exercises.models import Exercise
from quizzes.models import MockTest

pytestmark = pytest.mark.django_db
KEY = 'a' * 32
RUBRIC = {'solution': ['Step one.'], 'checkpoints': [{'id': 1, 'text': 'States the rule', 'basis': ''}],
          'mistakes': [], 'format': 'steps'}


def _set(user):
    made = [
        ('Câu 1. Chọn đáp án đúng.', {'kind': 'choice', 'answer': 'B',
                                      'options': [{'label': 'A', 'text': 'Một'}, {'label': 'B', 'text': 'Hai'}]}),
        ('Câu 2. Đúng hay sai?', {'kind': 'true_false', 'statements': [
            {'label': 'a', 'text': 'Một', 'answer': True}, {'label': 'b', 'text': 'Hai', 'answer': False},
            {'label': 'c', 'text': 'Ba', 'answer': True}, {'label': 'd', 'text': 'Bốn', 'answer': False}]}),
        ('Câu 3. Phân tử khối?', {'kind': 'short', 'answer': '-0,7', 'accept': ['-0.70']}),
        ('Câu 4. Giải thích.', {'kind': 'written', **RUBRIC}),
    ]
    return [Exercise.objects.create(user=user, notebook=None, origin='own', set_key=KEY, set_title='Đề Hoá HK1',
                                    prompt=prompt, reference={**RUBRIC, **ref}, figures=['data:image/png;base64,AA'])
            for prompt, ref in made]


def test_a_set_is_sat_as_a_timed_paper_worth_ten(client, user):
    _set(user)
    res = client.post(f'/api/exercises/sets/{KEY}/sit/')
    assert res.status_code == 201
    body = res.json()
    assert (body['template'], body['notebook'], body['notebook_title']) == ('paper', None, 'Đề Hoá HK1')
    paper = body['paper']
    assert [r['section'] for r in paper] == ['choice', 'true_false', 'short', 'written']
    assert round(sum(r['points'] for r in paper), 2) == 10
    assert paper[0]['options'] == ['A. Một', 'B. Hai']
    assert paper[0]['figures'] == ['data:image/png;base64,AA']
    assert all('correct_answer' not in r for r in paper)                # nothing given away while sitting
    assert all('answer' not in st for st in paper[1]['statements'])
    assert body['duration_minutes'] >= 10


def test_the_paper_is_marked_by_its_own_answers_and_misses_go_back(client, user):
    made = _set(user)
    body = client.post(f'/api/exercises/sets/{KEY}/sit/').json()
    rows = {r['section']: r['id'] for r in body['paper']}
    url = f"/api/quizzes/mock-tests/{body['id']}"
    client.post(f'{url}/answer/', {'paper_question_id': rows['choice'], 'answer': 'B. Hai'}, format='json')
    client.post(f'{url}/answer/', {'paper_question_id': rows['true_false'],
                                   'answer': {'a': True, 'b': False, 'c': True, 'd': True}}, format='json')
    client.post(f'{url}/answer/', {'paper_question_id': rows['short'], 'answer': '-0.7'}, format='json')

    review = client.post(f'{url}/submit/').json()

    marked = {r['section']: r for r in review['paper']}
    assert marked['choice']['is_correct'] and marked['short']['is_correct']          # -0.7 is -0,7
    assert not marked['true_false']['is_correct'] and marked['true_false']['earned'] > 0   # 3 of 4 statements
    assert not marked['written']['is_correct']                                       # left blank
    assert review['mistake_count'] == 2 and review['paper_title'] == 'Đề Hoá HK1'
    assert {p['section'] for p in review['parts']} == {'choice', 'true_false', 'short', 'written'}

    today = timezone.localdate()
    back = {e.id: (e.status, e.revisit_on) for e in Exercise.objects.filter(id__in=[m.id for m in made])}
    assert back[made[1].id] == ('revisit', today) and back[made[3].id] == ('revisit', today)
    assert back[made[0].id][0] == 'new'


def test_only_ones_own_set_can_be_sat(client, other_user):
    _set(other_user)
    assert client.post(f'/api/exercises/sets/{KEY}/sit/').status_code == 404
    assert not MockTest.objects.exists()


def test_a_real_papers_words_are_shown_as_printed(client, user):
    """No tidying of the paper's own text: "Zn – Cu" stays a dash."""
    Exercise.objects.create(user=user, notebook=None, origin='own', set_key=KEY, set_title='Đề',
                            prompt='Cho pin điện hoá Zn – Cu.', reference={'kind': 'written', **RUBRIC})
    Exercise.objects.create(user=user, notebook=None, origin='own', set_key=KEY, set_title='Đề',
                            prompt='Câu 2 — tính.', reference={'kind': 'written', **RUBRIC})
    paper = client.post(f'/api/exercises/sets/{KEY}/sit/').json()['paper']
    assert [r['question_text'] for r in paper] == ['Cho pin điện hoá Zn – Cu.', 'Câu 2 — tính.']
