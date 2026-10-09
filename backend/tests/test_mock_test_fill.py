"""Thi thử: xin bao nhiêu câu thì đề có đúng bấy nhiêu câu.

When the notebook holds fewer questions than the paper asks for, the
shortfall is generated before the paper is drawn. Each round adds to the
pool: it reads parts of the documents earlier rounds did not, is told what
is already asked, and once the material runs thin it asks about the same
facts from other angles rather than giving up.
"""
import re

import pytest

from notebooks.models import Notebook
from quizzes.models import Question, Quiz
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

URL = '/api/quizzes/mock-tests/'
LONG = ' '.join(f'Paragraph {i} explains how usability goal number {i % 7} is measured in study {i}.'
                for i in range(900))


class _Writer:
    """Writes as many new questions as it is asked for, all different."""
    name = 'stub'

    def __init__(self):
        self.prompts = []
        self.written = 0

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        n = int(re.search(r'Create exactly (\d+)', prompt).group(1))
        out = []
        for _ in range(n):
            self.written += 1
            out.append({'question_text': f'Which goal does study {self.written} measure?',
                        'correct_answer': f'goal {self.written}',
                        'distractors': [f'other {self.written}a', f'other {self.written}b', f'other {self.written}c'],
                        'explanation': 'From the passage.'})
        return {'questions': out}

    def summarize(self, text, title=''):
        return ''


@pytest.fixture
def writer(monkeypatch):
    w = _Writer()
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: w)
    return w


@pytest.fixture
def lecture(user):
    nb = Notebook.objects.create(user=user, title='HCI')
    make_source(nb, 'Lecture', LONG)
    return nb


def _start(client, nb, count):
    res = client.post(URL, {'notebook': nb.id, 'question_count': count, 'duration_minutes': 30}, format='json')
    assert res.status_code == 201, res.json()
    return res.json()


@pytest.mark.parametrize('count', [30, 50])
def test_the_paper_has_exactly_the_questions_asked_for(client, lecture, writer, count):
    paper = _start(client, lecture, count)

    assert paper['question_count'] == count
    assert len(paper['paper']) == count
    assert not paper.get('short_paper')


def test_no_question_appears_twice(client, lecture, writer):
    paper = _start(client, lecture, 30)

    texts = [q['question_text'] for q in paper['paper']]
    assert len(set(texts)) == len(texts)


def test_topping_up_adds_to_the_pool_instead_of_replacing_it(client, lecture, writer):
    _start(client, lecture, 30)

    live = Question.objects.filter(quiz__in=Quiz.objects.filter(user=lecture.user, is_published=True))
    assert live.count() >= 30


def test_each_round_is_told_what_is_already_asked(client, lecture, writer):
    _start(client, lecture, 30)

    later = [p for p in writer.prompts if 'already exist' in p]
    assert later, 'no round after the first'
    assert 'Which goal does study 1 measure?' in later[0]


def test_later_rounds_read_other_parts_of_the_document(client, lecture, writer):
    _start(client, lecture, 30)

    def passages(prompts):
        return {p for prompt in prompts for p in re.findall(r'Paragraph \d+', prompt)}
    first = [p for p in writer.prompts if 'already exist' not in p]
    later = [p for p in writer.prompts if 'already exist' in p]
    assert passages(later) - passages(first)


def test_thin_material_is_asked_about_from_other_angles(client, user, writer):
    # A short note, already made into a quiz: every passage it has has been
    # asked about once, so more questions must come from other angles.
    nb = Notebook.objects.create(user=user, title='Short')
    note = make_source(nb, 'Note', ' '.join(f'Fact {i}: cells divide by mitosis in step {i % 3}.' for i in range(60)))
    client.post(f'/api/notebooks/notebooks/{nb.id}/generate_quiz/',
                {'source_ids': [note.id], 'question_count': 8}, format='json')

    _start(client, nb, 20)

    assert 'from a different angle' in writer.prompts[-1]


def test_pressing_make_quiz_still_replaces_the_documents_quiz(client, lecture, writer):
    # Topping up a paper adds; the student's own "make a quiz" press keeps
    # replacing, so a document does not stack quizzes from repeated presses.
    ids = list(lecture.sources.values_list('id', flat=True))
    for _ in range(2):
        client.post(f'/api/notebooks/notebooks/{lecture.id}/generate_quiz/',
                    {'source_ids': ids, 'question_count': 8}, format='json')

    assert Quiz.objects.filter(user=lecture.user, is_published=True).count() == 1


def test_a_big_round_is_split_into_requests_a_model_answers_in_time(client, lecture, writer, settings):
    # One request for 32 questions timed out on every model (measured: 412s,
    # then nothing). No request asks for more than a model writes in time;
    # the rest go in parallel requests.
    _start(client, lecture, 30)

    sizes = [int(re.search(r'Create exactly (\d+)', p).group(1)) for p in writer.prompts]
    assert max(sizes) <= settings.GENERATE_PER_REQUEST
