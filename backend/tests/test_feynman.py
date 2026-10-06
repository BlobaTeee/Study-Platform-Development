"""Giải thích bằng lời của bạn: the student explains a concept they keep
forgetting, and gets back what was right, what is missing and what is
wrong — judged against the passages the cards came from, not general
knowledge, and in words rather than a score.
"""
import pytest

from flashcards.models import Flashcard
from study_sessions.models import FeynmanAttempt
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

URL = '/api/study/explain/'
PASSAGE = ('Usability goals concern how well a product works: it should be effective, '
           'efficient, safe and easy to learn. User experience goals concern how it feels.')
TEXT = 'Usability is about whether the product works well, like being efficient and safe.'

FEEDBACK = {
    'correct': ['Usability is about how well the product works'],
    'missing': ['Being easy to learn is also a usability goal'],
    'wrong': [{'claim': 'Usability means looking nice', 'correction': 'That is a UX goal'}],
    'level': 'most',
    'reread': [1],
}


class _Provider:
    name = 'stub'

    def __init__(self, reply=None, fail=False):
        self.reply = FEEDBACK if reply is None else reply
        self.fail = fail
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        if self.fail:
            from notebooks.services.gemini_client import GeminiNotConfiguredError
            raise GeminiNotConfiguredError('none')
        return self.reply

    def summarize(self, text, title=''):
        return ''


@pytest.fixture
def cards(user, notebook):
    source = make_source(notebook, 'HCI lecture', PASSAGE)
    out = []
    for q, a in [('What do usability goals concern?', 'How well it works'),
                 ('Name one usability goal', 'Easy to learn')]:
        card = Flashcard.objects.create(user=user, notebook=notebook, question=q, answer=a)
        card.sources.set([source])
        out.append(card)
    return out, source


@pytest.fixture
def provider(monkeypatch):
    p = _Provider()
    monkeypatch.setattr('study_sessions.feynman.get_ai_provider', lambda: p)
    return p


def _explain(client, card_ids, text=TEXT, concept='Usability goals'):
    return client.post(URL, {'card_ids': card_ids, 'concept': concept, 'text': text}, format='json')


def test_the_explanation_is_judged_against_the_cards_passages(client, cards, provider):
    (deck, _source) = cards
    res = _explain(client, [c.id for c in deck])

    assert res.status_code == 201, res.json()
    prompt = provider.prompts[-1]
    assert 'easy to learn' in prompt          # the passage
    assert TEXT in prompt                     # the student's words
    assert 'Usability goals' in prompt        # the concept
    body = res.json()
    assert body['correct'] == FEEDBACK['correct']
    assert body['missing'] == FEEDBACK['missing']
    assert body['wrong'] == FEEDBACK['wrong']
    assert body['level'] == 'most'


def test_the_passage_to_reread_names_its_document(client, cards, provider):
    (deck, source) = cards
    body = _explain(client, [c.id for c in deck]).json()

    assert body['reread'][0]['source_id'] == source.id
    assert body['reread'][0]['title'] == 'HCI lecture'
    assert body['reread'][0]['notebook_id'] == source.notebook_id
    assert 'effective' in body['reread'][0]['passage']


def test_the_attempt_is_kept_so_a_reload_does_not_lose_it(client, cards, provider):
    (deck, _source) = cards
    ids = [c.id for c in deck]
    _explain(client, ids)

    latest = client.get(URL, {'cards': ','.join(map(str, reversed(ids)))}).json()

    assert latest['text'] == TEXT
    assert latest['missing'] == FEEDBACK['missing']
    assert FeynmanAttempt.objects.count() == 1


def test_nothing_kept_yet_is_an_empty_answer(client, cards):
    (deck, _source) = cards
    assert client.get(URL, {'cards': str(deck[0].id)}).json() == {}


def test_an_odd_reply_is_cleaned_rather_than_shown_raw(client, cards, provider):
    (deck, _source) = cards
    provider.reply = {'correct': 'not a list', 'missing': ['', 'Easy to learn'],
                      'wrong': [{'claim': 'x'}, 'y'], 'level': 'brilliant', 'reread': [7, 'a']}

    body = _explain(client, [c.id for c in deck]).json()

    assert body['correct'] == []
    assert body['missing'] == ['Easy to learn']
    assert body['wrong'] == []
    assert body['level'] == 'most'           # something missing → not "solid"
    assert body['reread'] == []


@pytest.mark.parametrize('text', ['', 'too short'])
def test_a_few_words_are_not_an_explanation(client, cards, provider, text):
    (deck, _source) = cards
    assert _explain(client, [c.id for c in deck], text=text).status_code == 400
    assert provider.prompts == []


def test_only_my_own_cards(client, other_client, cards, provider):
    (deck, _source) = cards
    assert _explain(other_client, [c.id for c in deck]).status_code == 400
    assert provider.prompts == []


def test_without_a_provider_it_says_so_and_keeps_nothing(client, cards, monkeypatch):
    (deck, _source) = cards
    monkeypatch.setattr('study_sessions.feynman.get_ai_provider', lambda: _Provider(fail=True))

    res = _explain(client, [c.id for c in deck])

    assert res.status_code == 503
    assert res.json()['detail']
    assert FeynmanAttempt.objects.count() == 0
