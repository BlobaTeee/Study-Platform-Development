"""A card graded Hard is rewritten so the student cannot answer from memory
of the wording. The rewrite takes model calls (seconds each), so it must not
hold up the due-cards fetch that the home page and study page wait on: the
fetch answers with the cards as they are, and the rewrite lands for the next
fetch.
"""
import threading

import pytest

from flashcards.models import Flashcard
from study_sessions import views
from tests.test_daily_budget_api import DUE, _ids, _owe

# The rewrite runs on another thread with its own connection, so the rows it
# reads have to be committed.
pytestmark = pytest.mark.django_db(transaction=True)


class SlowProvider:
    """Answers only once released, like a model that takes its time."""

    def __init__(self):
        self.release = threading.Event()

    def generate_json(self, prompt):
        self.release.wait(10)
        return {'question': 'Which organelle makes most of the cell\'s ATP?', 'answer': 'Mitochondria'}


@pytest.fixture
def flagged(user, notebook):
    card = Flashcard.objects.create(user=user, notebook=notebook, question='What is the powerhouse of the cell?',
                                    answer='Mitochondria', needs_regeneration=True)
    _owe(user, card, result='hard')
    return card


@pytest.fixture
def provider(monkeypatch):
    p = SlowProvider()
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: p)
    return p


def test_the_fetch_does_not_wait_for_the_rewrite(client, settings, flagged, provider):
    settings.CARD_VARIANTS_IN_BACKGROUND = True

    res = client.get(DUE)                     # the provider is still holding its answer

    assert res.status_code == 200
    assert _ids(res) == [flagged.id]
    provider.release.set()
    views.wait_for_variants()


def test_the_rewrite_is_there_on_the_next_fetch(client, settings, flagged, provider):
    settings.CARD_VARIANTS_IN_BACKGROUND = True
    provider.release.set()

    client.get(DUE)
    views.wait_for_variants()
    res = client.get(DUE)

    flagged.refresh_from_db()
    assert flagged.archived
    body = res.json()
    assert [c['question'] for c in body] == ["Which organelle makes most of the cell's ATP?"]


def test_one_rewrite_at_a_time_per_student(client, settings, flagged, provider):
    settings.CARD_VARIANTS_IN_BACKGROUND = True

    client.get(DUE)
    client.get(DUE)                           # a second fetch while the first rewrite runs
    provider.release.set()
    views.wait_for_variants()

    assert Flashcard.objects.filter(question__startswith='Which organelle').count() == 1
