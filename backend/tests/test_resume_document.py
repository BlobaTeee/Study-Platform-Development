"""Ôn thẻ một tài liệu: thẻ đã nhớ thì không làm lại.

Ten cards, four remembered, the student leaves and comes back: the six not
yet done are what is left, not all ten. A card answered wrong comes back to
be studied again, as before. Generating still replaces the deck with ten
new cards (test_decks_api); this only changes what studying a document
offers.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from flashcards.models import Flashcard
from study_sessions.models import CardReview

pytestmark = pytest.mark.django_db

DUE = '/api/study/card-reviews/due_today/'


@pytest.fixture
def deck(user, notebook):
    source = notebook.sources.order_by('id').first()
    cards = []
    for i in range(10):
        card = Flashcard.objects.create(user=user, notebook=notebook,
                                        question=f'Question {i}?', answer=f'answer {i}')
        card.sources.set([source])
        cards.append(card)
    return source, cards


def _grade(user, cards, result):
    for card in cards:
        CardReview.record(user, card, result)


def _days_pass(cards):
    """Move the cards' schedules into the past, as if days had gone by."""
    yesterday = timezone.localdate() - timedelta(days=1)
    CardReview.objects.filter(flashcard__in=cards).update(next_review_date=yesterday)


def _queue(client, source=None):
    params = {'source': source.id} if source else {}
    return {c['id'] for c in client.get(DUE, params).json()}


def test_cards_already_remembered_are_not_done_again(client, user, deck):
    source, cards = deck
    _grade(user, cards[:4], 'good')
    _days_pass(cards[:4])        # even once they would be due again

    assert _queue(client, source) == {c.id for c in cards[4:]}


def test_easy_counts_as_remembered_too(client, user, deck):
    source, cards = deck
    _grade(user, cards[:2], 'easy')
    _days_pass(cards[:2])

    assert _queue(client, source) == {c.id for c in cards[2:]}


def test_a_forgotten_card_comes_back_as_before(client, user, deck):
    source, cards = deck
    _grade(user, cards[:1], 'hard')
    _days_pass(cards[:1])

    assert cards[0].id in _queue(client, source)


def test_a_card_forgotten_then_remembered_is_done(client, user, deck):
    source, cards = deck
    _grade(user, cards[:1], 'hard')
    _grade(user, cards[:1], 'good')
    _days_pass(cards[:1])

    assert cards[0].id not in _queue(client, source)


def test_every_card_remembered_leaves_nothing_to_do(client, user, deck):
    source, cards = deck
    _grade(user, cards, 'good')
    _days_pass(cards)

    assert _queue(client, source) == set()


def test_the_workspace_is_told_how_many_cards_are_not_done(client, user, notebook, deck):
    source, cards = deck
    _grade(user, cards[:4], 'good')

    counts = client.get(f'/api/notebooks/notebooks/{notebook.id}/material_counts/'
                        f'?source_ids={source.id}').json()

    assert counts['flashcards'] == 10
    assert counts['to_do'] == 6
