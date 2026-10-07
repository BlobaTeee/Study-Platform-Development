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


def _notebooks(client):
    res = client.get(URL)
    assert res.status_code == 200, res.content
    return res.json()['notebooks']


def _groups(client):
    """Every concept group, across notebooks, in the order they are listed."""
    return [g for nb in _notebooks(client) for g in nb['groups']]


def test_forgotten_cards_are_grouped_by_concept_biggest_first(client, user, notebook):
    phones = _cards(user, notebook, PHONES, 'hard')
    cars = _cards(user, notebook, CARS, 'hard')

    groups = _groups(client)

    assert [g['count'] for g in groups] == [3, 2]
    assert set(groups[0]['card_ids']) == {c.id for c in phones}
    assert set(groups[1]['card_ids']) == {c.id for c in cars}
    assert groups[0]['label']
    assert groups[0]['sample'] in {q for q, _ in PHONES}


def test_a_card_that_fits_no_group_is_its_own_group(client, user, notebook):
    # No provider in tests: a card the clusters leave out stands alone, named
    # by its own words, so it can still be explained.
    _cards(user, notebook, PHONES, 'hard')
    lone = _cards(user, notebook, LONE, 'hard')

    groups = _groups(client)

    assert groups[-1]['card_ids'] == [lone[0].id]
    assert groups[-1]['label']
    assert 'other' not in groups[-1]


EMOTION = [
    ('What kind of features should be prioritized to avoid passively displaying information?',
     'Features for direct action'),
    ('Emotional goals should belong in the ___ process itself, not as an afterthought.', 'requirements'),
    ('What approach to app design produced stronger engagement than a purely functional approach?',
     'Emotion-led design approach'),
]


class _Grouper:
    """Stands in for the model: groups the cards it is shown."""
    name = 'stub'

    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def generate_json(self, prompt):
        self.calls += 1
        return self.reply

    def summarize(self, text, title=''):
        return ''


def _use(monkeypatch, provider):
    monkeypatch.setattr('study_sessions.forgotten.get_ai_provider', lambda: provider)


def test_cards_the_words_miss_are_grouped_by_meaning(client, user, notebook, monkeypatch):
    # Three cards on one idea, in words too different for the clusters.
    cards = _cards(user, notebook, EMOTION, 'hard')
    _use(monkeypatch, _Grouper({'groups': [{'label': 'Emotion-led design', 'cards': [1, 2, 3]}]}))

    groups = _groups(client)

    assert len(groups) == 1
    assert groups[0]['label'] == 'Emotion-led design'
    assert set(groups[0]['card_ids']) == {c.id for c in cards}


def test_a_muddled_grouping_still_lists_every_card_once(client, user, notebook, monkeypatch):
    cards = _cards(user, notebook, EMOTION, 'hard')
    # Card 2 twice, card 3 never, a card that does not exist, a group with no name.
    _use(monkeypatch, _Grouper({'groups': [{'label': 'A', 'cards': [1, 2]},
                                           {'label': '', 'cards': [2, 9]}]}))

    listed = [i for g in _groups(client) for i in g['card_ids']]

    assert sorted(listed) == sorted(c.id for c in cards)


def test_the_grouping_is_remembered_so_a_reload_costs_nothing(client, user, notebook, monkeypatch):
    _cards(user, notebook, EMOTION, 'hard')
    grouper = _Grouper({'groups': [{'label': 'Emotion-led design', 'cards': [1, 2, 3]}]})
    _use(monkeypatch, grouper)

    _groups(client)
    _groups(client)

    assert grouper.calls == 1


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

    assert other_client.get(URL).json()['notebooks'] == []


def test_a_failed_grouping_is_tried_again_next_time(client, user, notebook, monkeypatch):
    cards = _cards(user, notebook, EMOTION, 'hard')
    _groups(client)    # no provider: one card per group, and nothing remembered

    _use(monkeypatch, _Grouper({'groups': [{'label': 'Emotion-led design', 'cards': [1, 2, 3]}]}))
    groups = _groups(client)

    assert [set(g['card_ids']) for g in groups] == [{c.id for c in cards}]


# ---- by notebook ---------------------------------------------------------------

def test_groups_are_listed_under_their_notebook_most_forgotten_first(client, user, notebook):
    from notebooks.models import Notebook
    from tests.conftest import make_source
    other = Notebook.objects.create(user=user, title='Transport')
    make_source(other, 'Cars')
    phones = _cards(user, notebook, PHONES, 'hard')
    cars = _cards(user, other, CARS, 'hard')

    listed = _notebooks(client)

    assert [nb['notebook_id'] for nb in listed] == [notebook.id, other.id]
    assert listed[0]['title'] == notebook.title
    assert listed[0]['count'] == 3
    assert set(listed[0]['card_ids']) == {c.id for c in phones}
    assert set(listed[1]['card_ids']) == {c.id for c in cars}


def test_cards_of_two_notebooks_never_share_a_group(client, user, notebook, monkeypatch):
    from notebooks.models import Notebook
    from tests.conftest import make_source
    other = Notebook.objects.create(user=user, title='Copy')
    make_source(other, 'Phones again')
    _cards(user, notebook, PHONES[:2], 'hard')
    _cards(user, other, PHONES[2:] + [PHONES[0]], 'hard')   # same idea, other notebook

    for nb in _notebooks(client):
        ids = {i for g in nb['groups'] for i in g['card_ids']}
        assert ids == set(nb['card_ids'])
