"""Đáp án ngắn để nhớ, phần giải thích để hiểu.

A card's answer is what the student recalls, so it is kept to a short
phrase; the full sentence moves to a separate explanation shown under it.
A question that wants a long list is split into several cards instead.
"""
import pytest

from flashcards.models import Flashcard
from flashcards.services.regeneration import replace_card
from flashcards.services.variant_generator import _clean, build_variant_prompt
from study_sessions.models import CardReview

pytestmark = pytest.mark.django_db

CARD = {'question': 'How do UX goals differ from usability goals?',
        'answer': 'UX: how it feels; usability: how well it works',
        'explanation': 'Usability goals are about efficiency and safety, UX goals about the experience.',
        'difficulty': 'medium'}


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


def _generate(client, notebook, monkeypatch, cards):
    provider = _Provider(cards)
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)
    ids = list(notebook.sources.values_list('id', flat=True))
    res = client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_flashcards/',
                      {'source_ids': ids, 'count': 1}, format='json')
    assert res.status_code == 201, res.json()
    return provider


def test_the_prompt_asks_for_a_short_answer_and_a_separate_explanation(client, notebook, monkeypatch):
    prompt = _generate(client, notebook, monkeypatch, [CARD]).prompts[-1]

    assert '"explanation"' in prompt
    assert '12 words' in prompt
    assert 'separate flashcards' in prompt   # long lists are split, not crammed


def test_the_explanation_is_kept_and_served_with_the_card(client, notebook, monkeypatch):
    _generate(client, notebook, monkeypatch, [CARD])

    card = Flashcard.objects.get(question=CARD['question'])
    assert card.explanation == CARD['explanation']
    listed = client.get('/api/flashcards/flashcards/').json()
    listed = listed.get('results', listed) if isinstance(listed, dict) else listed
    assert listed[0]['explanation'] == CARD['explanation']
    due = client.get('/api/study/card-reviews/due_today/').json()
    assert due[0]['explanation'] == CARD['explanation']


def test_a_card_without_an_explanation_still_saves(client, notebook, monkeypatch):
    _generate(client, notebook, monkeypatch, [{k: v for k, v in CARD.items() if k != 'explanation'}])

    assert Flashcard.objects.get(question=CARD['question']).explanation == ''


def test_a_variant_follows_the_same_rules_and_keeps_its_explanation(user, notebook):
    prompt = build_variant_prompt('Q?', 'A', '')
    assert '"explanation"' in prompt and '12 words' in prompt

    variant = _clean({**CARD, 'question': 'Why do UX goals matter?'})
    assert variant['explanation'] == CARD['explanation']

    old = Flashcard.objects.create(user=user, notebook=notebook, question='Q?', answer='A')
    CardReview.record(user, old, 'hard')
    assert replace_card(old, variant).explanation == CARD['explanation']
