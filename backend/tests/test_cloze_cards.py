"""Thẻ điền chỗ trống: một câu trong tài liệu, che đi một từ khoá.

They are mixed into an ordinary deck. A cloze card the model got wrong —
no blank, several blanks, or the hidden word still visible — is left out
rather than shown as a puzzle with no answer.
"""
import pytest

from flashcards.models import Flashcard

pytestmark = pytest.mark.django_db

CLOZE = {'kind': 'cloze',
         'question': 'Usability goals measure whether a product is _____, safe and easy to learn.',
         'answer': 'effective', 'explanation': 'x', 'difficulty': 'easy'}
BASIC = {'question': 'What do UX goals describe?', 'answer': 'How the experience feels',
         'explanation': 'x', 'difficulty': 'medium'}


class _Provider:
    name = 'stub'

    def __init__(self, cards):
        self.cards = cards
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return {'flashcards': self.cards}

    def summarize(self, text, title=''):
        return ''


def _generate(client, notebook, monkeypatch, cards, count=5):
    provider = _Provider(cards)
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)
    ids = list(notebook.sources.values_list('id', flat=True))
    res = client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_flashcards/',
                      {'source_ids': ids, 'count': count}, format='json')
    return provider, res


def test_the_prompt_asks_for_some_fill_in_the_blank_cards(client, notebook, monkeypatch):
    provider, _ = _generate(client, notebook, monkeypatch, [BASIC])
    prompt = provider.prompts[-1]

    assert '"kind": "basic|cloze"' in prompt
    assert '___' in prompt


def test_a_cloze_card_is_saved_with_one_plain_blank(client, notebook, monkeypatch):
    _, res = _generate(client, notebook, monkeypatch, [CLOZE, BASIC])
    assert res.status_code == 201

    cloze = Flashcard.objects.get(kind='cloze')
    assert cloze.question == 'Usability goals measure whether a product is ___, safe and easy to learn.'
    assert cloze.answer == 'effective'
    assert Flashcard.objects.get(question=BASIC['question']).kind == 'basic'


@pytest.mark.parametrize('broken', [
    {**CLOZE, 'question': 'Usability goals measure whether a product is effective.'},       # no blank
    {**CLOZE, 'question': 'Usability goals are ___, ___ and easy to learn.'},              # two blanks
    {**CLOZE, 'question': 'An effective product is ___, safe and easy to learn.'},         # answer visible
    {**CLOZE, 'answer': 'effective in every one of the situations it is used in'},         # not a key term
    {**CLOZE, 'answer': ''},
])
def test_a_broken_cloze_card_is_left_out(client, notebook, monkeypatch, broken):
    _, res = _generate(client, notebook, monkeypatch, [broken, BASIC])

    assert res.status_code == 201
    assert list(Flashcard.objects.values_list('question', flat=True)) == [BASIC['question']]


def test_the_kind_is_served_with_the_card(client, notebook, monkeypatch):
    _generate(client, notebook, monkeypatch, [CLOZE])

    listed = client.get('/api/flashcards/flashcards/').json()
    listed = listed.get('results', listed) if isinstance(listed, dict) else listed
    assert listed[0]['kind'] == 'cloze'
    assert client.get('/api/study/card-reviews/due_today/').json()[0]['kind'] == 'cloze'


def test_an_edit_cannot_remove_the_blank(client, user, notebook):
    card = Flashcard.objects.create(user=user, notebook=notebook, kind='cloze',
                                    question='A product is ___, safe.', answer='effective')
    url = f'/api/flashcards/flashcards/{card.id}/'

    bad = client.put(url, {'question': 'A product is effective, safe.', 'answer': 'effective'}, format='json')
    good = client.put(url, {'question': 'A good product is ___.', 'answer': 'effective'}, format='json')

    assert bad.status_code == 400
    assert good.status_code == 200
    card.refresh_from_db()
    assert card.question == 'A good product is ___.'
