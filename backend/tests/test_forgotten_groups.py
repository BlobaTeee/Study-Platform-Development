"""Thẻ hay quên: the cards a student is forgetting right now, by concept.

A card counts as forgotten while its newest grade is "hard". Getting it
right again takes it off the list. A card swapped for a fresh variant keeps
its place, because the variant carries the same unanswered concept.
"""
import pytest

from flashcards.models import Flashcard
from flashcards.services.regeneration import replace_card
from study_sessions.models import CardReview

pytestmark = pytest.mark.django_db

URL = '/api/study/card-reviews/forgotten_groups/'

PHONES = [
    ('What role do mobile phones play in the personal safety of homeless young people?', 'A lifeline'),
    ('What does a mobile phone serve as for homeless young people?', 'A safety device'),
    ('How does phone theft affect the safety benefit of mobile phones for homeless youth?', 'It removes it'),
]
CARS = [
    ('What is one of the ethical issues that self-driving cars must address?', 'Whom to protect'),
    ('Why must self-driving cars decide whom to protect in an unavoidable accident?', 'No driver decides'),
]
LONE = [('What was the final sample size of national AI policy strategies?', '24')]


def _cards(user, notebook, pairs, *grades):
    cards = []
    for q, a in pairs:
        card = Flashcard.objects.create(user=user, notebook=notebook, question=q, answer=a)
        for grade in grades:
            CardReview.record(user, card, grade)
        cards.append(card)
    return cards


def _groups(client):
    res = client.get(URL)
    assert res.status_code == 200, res.content
    return res.json()['groups']


def test_forgotten_cards_are_grouped_by_concept_biggest_first(client, user, notebook):
    phones = _cards(user, notebook, PHONES, 'hard')
    cars = _cards(user, notebook, CARS, 'hard')

    groups = _groups(client)

    assert [g['count'] for g in groups] == [3, 2]
    assert set(groups[0]['card_ids']) == {c.id for c in phones}
    assert set(groups[1]['card_ids']) == {c.id for c in cars}
    assert groups[0]['label']
    assert groups[0]['sample'] in {q for q, _ in PHONES}


def test_a_card_that_fits_no_group_is_still_listed(client, user, notebook):
    _cards(user, notebook, PHONES, 'hard')
    lone = _cards(user, notebook, LONE, 'hard')

    groups = _groups(client)

    assert groups[-1]['card_ids'] == [lone[0].id]
    assert groups[-1]['other'] is True
    assert groups[0]['other'] is False


def test_a_card_remembered_since_is_not_forgotten(client, user, notebook):
    _cards(user, notebook, PHONES, 'hard', 'good')
    _cards(user, notebook, CARS, 'good')

    assert _groups(client) == []


def test_a_card_forgotten_after_being_remembered_is_forgotten(client, user, notebook):
    cars = _cards(user, notebook, CARS, 'easy', 'hard')

    assert set(_groups(client)[0]['card_ids']) == {c.id for c in cars}


def test_a_replaced_card_stays_forgotten_through_its_variant(client, user, notebook):
    phones = _cards(user, notebook, PHONES, 'hard')
    variant = replace_card(phones[0], {'question': 'Why do homeless youth carry mobile phones?',
                                       'answer': 'For safety'})

    ids = {i for g in _groups(client) for i in g['card_ids']}

    assert variant.id in ids
    assert phones[0].id not in ids   # archived; the variant stands in for it


def test_only_my_own_reviews_count(client, other_client, user, notebook):
    _cards(user, notebook, PHONES, 'hard')

    assert other_client.get(URL).json()['groups'] == []
