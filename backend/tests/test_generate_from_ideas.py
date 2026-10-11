"""Cards, quizzes and mock tests are written from the document's main ideas.

Each request carries ideas with the passage each came from, core ideas
first, instead of three passages picked by word statistics. A question
still points at the passage it was written from. When the ideas cannot be
read (no provider at the time), generation falls back to passages.
"""
import re

import pytest

from flashcards.models import Flashcard
from notebooks.models import Notebook, Source
from quizzes.models import Question
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

START = 'Mobile phones are a lifeline for homeless young people. '
FILLER = 'This sentence only fills space in the middle of the lecture. ' * 400
END = 'Depleted batteries undermine the safety a phone provides. '
DOC = START * 3 + FILLER + END * 3

POINTS = [
    {'point': 'Phones are a lifeline for homeless youth.', 'importance': 'core',
     'quote': 'Mobile phones are a lifeline for homeless young people.'},
    {'point': 'Flat batteries cancel that safety.', 'importance': 'core',
     'quote': 'Depleted batteries undermine the safety a phone provides.'},
]


class _Model:
    """Reads documents into POINTS and writes as many items as asked."""
    name = 'stub'

    def __init__(self, can_read=True):
        self.can_read = can_read
        self.reads = 0
        self.prompts = []
        self.n = 0

    def generate_json(self, prompt):
        if '"key_points"' in prompt:
            self.reads += 1
            if not self.can_read:
                raise RuntimeError('down')
            return {'summary': 'An overview.', 'key_points': POINTS}
        self.prompts.append(prompt)
        n = int(re.search(r'Create exactly (\d+)', prompt).group(1))
        out = []
        for i in range(n):
            self.n += 1
            about = 'batteries' if i % 2 else 'lifeline'
            out.append({'question': f'Card {self.n} about the {about}?', 'answer': f'a{self.n}',
                        'question_text': f'Question {self.n} about the {about}?', 'correct_answer': f'c{self.n}',
                        'distractors': [f'x{self.n}', f'y{self.n}', f'z{self.n}'], 'explanation': 'e'})
        return {'flashcards': out, 'questions': out}

    def summarize(self, text, title=''):
        return ''


@pytest.fixture
def model(monkeypatch):
    m = _Model()
    for target in ('notebooks.services.generate.get_ai_provider', 'notebooks.services.key_points.get_ai_provider'):
        monkeypatch.setattr(target, lambda: m)
    return m


@pytest.fixture
def lecture(user):
    nb = Notebook.objects.create(user=user, title='HCI')
    return nb, make_source(nb, 'Lecture', DOC)


def _deck(client, nb, source):
    return client.post(f'/api/notebooks/notebooks/{nb.id}/generate_flashcards/',
                       {'source_ids': [source.id], 'count': 10}, format='json')


def _quiz(client, nb, source):
    return client.post(f'/api/notebooks/notebooks/{nb.id}/generate_quiz/',
                       {'source_ids': [source.id], 'question_count': 8}, format='json')


def test_a_deck_is_written_from_the_main_ideas(client, lecture, model):
    nb, source = lecture
    assert _deck(client, nb, source).status_code == 201

    prompt = model.prompts[-1]
    assert 'main ideas' in prompt
    assert 'Phones are a lifeline for homeless youth.' in prompt
    # The idea from the end of the document, past where passages used to stop.
    assert 'Flat batteries cancel that safety.' in prompt


def test_a_quiz_is_written_from_the_main_ideas_and_keeps_its_passage(client, lecture, model):
    nb, source = lecture
    assert _quiz(client, nb, source).status_code == 201

    assert 'Flat batteries cancel that safety.' in model.prompts[-1]
    questions = list(Question.objects.all())
    assert questions and all(q.source_id == source.id for q in questions)
    battery = [q for q in questions if 'batteries' in q.question_text]
    assert battery and 'Depleted batteries' in battery[0].source_excerpt
    assert '###' not in battery[0].source_excerpt


def test_the_document_is_read_only_once(client, lecture, model):
    nb, source = lecture
    _deck(client, nb, source)
    _quiz(client, nb, source)

    assert model.reads == 1
    assert len(Source.objects.get(id=source.id).key_points) == 2


def test_without_main_ideas_generation_falls_back_to_passages(client, lecture, monkeypatch):
    m = _Model(can_read=False)
    for target in ('notebooks.services.generate.get_ai_provider', 'notebooks.services.key_points.get_ai_provider'):
        monkeypatch.setattr(target, lambda: m)
    nb, source = lecture

    assert _deck(client, nb, source).status_code == 201
    assert 'main ideas' not in m.prompts[-1]
    assert Flashcard.objects.filter(archived=False).exists()


def test_a_mock_test_round_after_the_first_asks_from_other_angles(client, lecture, model):
    nb, source = lecture
    _quiz(client, nb, source)

    res = client.post('/api/quizzes/mock-tests/', {'notebook': nb.id, 'question_count': 20,
                                                   'duration_minutes': 30}, format='json')

    assert res.status_code == 201, res.json()
    assert res.json()['question_count'] == 20
    later = model.prompts[-1]
    assert 'already exist' in later and 'from a different angle' in later
