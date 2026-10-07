"""Tạo thêm thẻ, không tạo lại: a document's deck grows, it is never swapped.

Generating again keeps the cards already there and their schedules, and
adds cards on what the deck does not ask yet. A document still holding a
full batch it has not started gets no more until those are done, so a
press-happy afternoon cannot bury the queue. Studying a document finishes
its first pass before anything comes round again: ten cards, five done,
the next visit is the other five.
"""
import re
from datetime import timedelta

import pytest
from django.utils import timezone

from flashcards.models import Flashcard
from notebooks.services.deck_limits import MAX_CARDS_PER_SOURCE
from study_sessions.models import CardReview

pytestmark = pytest.mark.django_db

DUE = '/api/study/card-reviews/due_today/'


class _Writer:
    """Writes `n` new cards per call, numbered on from the last call."""
    name = 'stub'

    def __init__(self, repeat=None):
        self.prompts = []
        self.written = 0
        self.repeat = repeat     # a question to slip into every batch

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        n = int(re.search(r'Create exactly (\d+)', prompt).group(1))
        cards = [{'question': f'Question number {self.written + i}?', 'answer': f'answer {i}'}
                 for i in range(n)]
        self.written += n
        if self.repeat:
            cards[0] = {'question': self.repeat, 'answer': 'again'}
        return {'flashcards': cards}

    def summarize(self, text, title=''):
        return ''


@pytest.fixture
def writer(monkeypatch):
    w = _Writer()
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: w)
    return w


@pytest.fixture
def cells(notebook):
    return notebook.sources.order_by('id').first()


def _generate(client, notebook, source, count=MAX_CARDS_PER_SOURCE):
    return client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_flashcards/',
                       {'source_ids': [source.id], 'count': count}, format='json')


def _live(source):
    return list(Flashcard.objects.filter(sources=source, archived=False).order_by('id'))


def _study(user, cards, grade='good'):
    for card in cards:
        CardReview.record(user, card, grade)


def _make_due(cards):
    """Move the cards' schedules into the past, as if days had gone by."""
    yesterday = timezone.localdate() - timedelta(days=1)
    CardReview.objects.filter(flashcard__in=cards).update(next_review_date=yesterday)


# ---- generating more -----------------------------------------------------------

def test_generating_again_keeps_the_deck_and_adds_to_it(client, user, notebook, cells, writer):
    assert _generate(client, notebook, cells).status_code == 201
    first = _live(cells)
    _study(user, first)

    assert _generate(client, notebook, cells).status_code == 201

    live = _live(cells)
    assert len(live) == 2 * len(first)
    assert set(c.id for c in first) <= set(c.id for c in live)
    # The schedule earned on the first batch is still there.
    assert CardReview.objects.filter(flashcard__in=first).count() == len(first)


def test_the_new_batch_is_told_what_is_already_asked(client, user, notebook, cells, writer):
    _generate(client, notebook, cells)
    _study(user, _live(cells))

    _generate(client, notebook, cells)

    assert 'Question number 0?' in writer.prompts[-1]


def test_a_question_the_deck_already_asks_is_not_added_twice(client, user, notebook, cells, monkeypatch):
    w = _Writer()
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: w)
    _generate(client, notebook, cells)
    _study(user, _live(cells))
    w.repeat = 'Question number 0?'

    _generate(client, notebook, cells)

    questions = [c.question for c in _live(cells)]
    assert questions.count('Question number 0?') == 1


def test_a_full_batch_not_yet_started_gets_no_more(client, user, notebook, cells, writer):
    _generate(client, notebook, cells)
    asked = len(writer.prompts)

    res = _generate(client, notebook, cells)

    assert res.status_code == 400
    assert res.json()['detail']
    assert len(_live(cells)) == MAX_CARDS_PER_SOURCE
    assert len(writer.prompts) == asked          # no model call spent on it


def test_the_workspace_is_told_how_many_cards_are_not_started(client, user, notebook, cells, writer):
    _generate(client, notebook, cells)
    _study(user, _live(cells)[:4])

    counts = client.get(f'/api/notebooks/notebooks/{notebook.id}/material_counts/'
                        f'?source_ids={cells.id}').json()

    assert counts['flashcards'] == MAX_CARDS_PER_SOURCE
    assert counts['unseen'] == MAX_CARDS_PER_SOURCE - 4


# ---- studying a document ---------------------------------------------------------

def test_a_document_finishes_its_first_pass_before_anything_comes_round(client, user, notebook, cells, writer):
    _generate(client, notebook, cells)
    deck = _live(cells)
    done, left = deck[:5], deck[5:]
    _study(user, done)
    _make_due(done)          # the next day: the first five are due again

    queue = client.get(DUE, {'source': cells.id}).json()

    assert {c['id'] for c in queue} == {c.id for c in left}


def test_once_every_card_is_started_the_schedule_takes_over(client, user, notebook, cells, writer):
    _generate(client, notebook, cells)
    deck = _live(cells)
    _study(user, deck)
    _make_due(deck[:3])

    queue = client.get(DUE, {'source': cells.id}).json()

    assert {c['id'] for c in queue} == {c.id for c in deck[:3]}
