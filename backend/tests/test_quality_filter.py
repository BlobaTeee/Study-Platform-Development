"""Câu hỏi hỏng không tới tay người học khi còn câu tốt để thay.

Generation asks for a few more questions than the quiz needs, ranks them with
the quality check, and keeps the best. A quiz is never short because of it:
when there are not enough sound questions the least flawed fill the gap.
"""
import re

import pytest

from notebooks.models import Notebook
from quizzes.models import Question
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

PASSAGE = (
    "Mobile phones function simultaneously as a lifeline and as a source of risk. "
    "They let young people summon help in emergencies, remain in contact with trusted "
    "others and manage dangerous situations. Phone theft, loss, damage, depleted "
    "batteries and the cost of service repeatedly undermine that safety benefit."
)

# "a lifeline" is true according to the passage: two right answers.
RIVAL = {'question_text': 'What role do mobile phones play in personal safety?',
         'correct_answer': 'a source of risk',
         'distractors': ['a lifeline', 'a way to pay rent', 'a school requirement'],
         'explanation': 'x'}


def _clean(i):
    return {'question_text': f'Which problem undermines phone safety, case {i}?',
            'correct_answer': 'depleted batteries',
            'distractors': ['slow internet', 'small screens', 'loud ringtones'],
            'explanation': 'x'}


def _rival(i):
    return {**RIVAL, 'question_text': f'What role do mobile phones play in personal safety, case {i}?'}


class _Provider:
    name = 'stub'

    def __init__(self, make):
        self.make = make
        self.asked = []

    def generate_json(self, prompt):
        n = int(re.search(r'Create exactly (\d+)', prompt).group(1))
        self.asked.append(n)
        return {'questions': self.make(n)}

    def summarize(self, text, title=''):
        return ''


@pytest.fixture
def phones(user):
    nb = Notebook.objects.create(user=user, title='Safety')
    return nb, make_source(nb, 'Phones', PASSAGE)


def _generate(client, notebook, source, count=4):
    res = client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_quiz/',
                      {'source_ids': [source.id], 'question_count': count}, format='json')
    assert res.status_code == 201, res.json()
    return list(Question.objects.filter(quiz__user=notebook.user).order_by('order'))


def test_a_question_with_two_right_answers_is_left_out(client, phones, monkeypatch):
    provider = _Provider(lambda n: [RIVAL] + [_clean(i) for i in range(n - 1)])
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)
    nb, source = phones

    questions = _generate(client, nb, source, count=4)

    assert len(questions) == 4
    assert RIVAL['question_text'] not in {q.question_text for q in questions}


def test_a_few_extra_questions_are_asked_for(client, phones, monkeypatch):
    provider = _Provider(lambda n: [_clean(i) for i in range(n)])
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)
    nb, source = phones

    _generate(client, nb, source, count=4)

    # Room to leave a flawed question out without the quiz coming up short.
    assert sum(provider.asked) > 4


def test_the_quiz_is_never_short_when_every_question_is_flawed(client, phones, monkeypatch):
    provider = _Provider(lambda n: [_rival(i) for i in range(n)])
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)
    nb, source = phones

    assert len(_generate(client, nb, source, count=4)) == 4


def test_the_quiz_keeps_exactly_the_count_asked_for(client, phones, monkeypatch):
    provider = _Provider(lambda n: [_clean(i) for i in range(n)])
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)
    nb, source = phones

    assert len(_generate(client, nb, source, count=4)) == 4
