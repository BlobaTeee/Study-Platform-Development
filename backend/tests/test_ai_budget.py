"""Lượt gọi AI là thứ có hạn: gói miễn phí cho mỗi model 20 lượt một ngày.

Making a deck or a quiz sends the document's passages in one request rather
than one request per passage. The coverage is the same; the cost is a
third. `GENERATE_CALLS` raises it again where requests are plentiful and
parallel answers are worth more than the quota.
"""
import re

import pytest

from notebooks.models import Notebook
from notebooks.services.generate import _document_chunks
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

LONG = ' '.join(f'Paragraph {i} discusses usability goal number {i % 7} and how designers '
                f'measure it in study {i}.' for i in range(900))


class _Counter:
    name = 'stub'

    def __init__(self):
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        n = int(re.search(r'Create exactly (\d+)', prompt).group(1))
        return {
            'flashcards': [{'question': f'Q{len(self.prompts)}-{i}?', 'answer': f'a{i}'} for i in range(n)],
            'questions': [{'question_text': f'Which goal {len(self.prompts)}-{i}?', 'correct_answer': f'goal {i}',
                           'distractors': ['x', 'y', 'z'], 'explanation': 'e'} for i in range(n)],
        }

    def summarize(self, text, title=''):
        return ''


@pytest.fixture
def lecture(user):
    nb = Notebook.objects.create(user=user, title='HCI')
    return nb, make_source(nb, 'Lecture', LONG)


@pytest.fixture
def counter(monkeypatch):
    c = _Counter()
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: c)
    return c


def _post(client, nb, source, what):
    body = {'source_ids': [source.id], 'count': 10, 'question_count': 8}
    res = client.post(f'/api/notebooks/notebooks/{nb.id}/generate_{what}/', body, format='json')
    assert res.status_code == 201, res.json()
    return res


@pytest.mark.parametrize('what', ['flashcards', 'quiz'])
def test_making_a_deck_or_quiz_is_one_request(client, lecture, counter, what):
    nb, source = lecture
    assert len(_document_chunks([source])) > 1      # a document long enough to split

    _post(client, nb, source, what)

    assert len(counter.prompts) == 1


def test_the_one_request_carries_every_passage(client, lecture, counter):
    nb, source = lecture

    _post(client, nb, source, 'flashcards')

    for passage in _document_chunks([source]):
        assert passage.strip()[:200] in counter.prompts[0]


def test_more_requests_can_be_allowed(client, lecture, counter, settings):
    settings.GENERATE_CALLS = 3
    nb, source = lecture

    _post(client, nb, source, 'flashcards')

    assert len(counter.prompts) == len(_document_chunks([source]))
