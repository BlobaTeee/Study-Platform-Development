"""Asking the tutor about a card you just got wrong: grounded, bounded."""
import pytest

from flashcards.models import Flashcard

pytestmark = pytest.mark.django_db

# Long enough to chunk: rivers, then the one paragraph the card is about, then mountains.
SOURCE = (' '.join(f'River sentence {i} describes a river in some detail for the reader.' for i in range(40))
          + ' Paris has been the capital of France since 508, when Clovis I made it his seat. '
          'Lyon was the capital of Roman Gaul before that. '
          + ' '.join(f'Mountain sentence {i} describes a mountain in some detail for the reader.' for i in range(40)))


def _card(user, notebook, source_text=SOURCE):
    from tests.conftest import make_source
    src = make_source(notebook, 'History', text=source_text)
    card = Flashcard.objects.create(user=user, notebook=notebook, question='Capital of France?', answer='Paris')
    card.sources.set([src])
    return card


class Tutor:
    name = 'stub'
    prompts: list = []

    def generate_json(self, prompt):
        Tutor.prompts.append(prompt)
        return {'answer': 'Clovis I chose Paris in 508; Lyon was only the Roman-era capital.'}


@pytest.fixture
def tutor(monkeypatch):
    Tutor.prompts = []
    monkeypatch.setattr('flashcards.services.tutor.get_ai_provider', lambda: Tutor())
    return Tutor


def _ask(client, card, question, history=None):
    return client.post(f'/api/flashcards/flashcards/{card.id}/ask/',
                       {'question': question, 'history': history or []}, format='json')


def test_the_answer_is_grounded_in_the_cards_own_passage(client, user, notebook, tutor):
    card = _card(user, notebook)

    res = _ask(client, card, 'Why not Lyon?')

    assert res.status_code == 200
    assert res.json()['answer'].startswith('Clovis I')
    prompt = tutor.prompts[0]
    assert 'Clovis I' in prompt                      # the passage went along
    assert 'Capital of France?' in prompt and 'Paris' in prompt and 'Why not Lyon?' in prompt
    assert 'River sentence 2 ' not in prompt and 'Mountain sentence 38' not in prompt   # one chunk, not the document


def test_the_tutor_answers_in_the_language_the_student_asked_in(client, user, notebook, tutor):
    card = _card(user, notebook)                      # English passage
    _ask(client, card, 'Giải thích đơn giản hơn được không?')
    assert 'Answer in Vietnamese' in tutor.prompts[0]


def test_earlier_turns_travel_with_the_question(client, user, notebook, tutor):
    card = _card(user, notebook)
    history = [{'role': 'user', 'text': 'Why not Lyon?'},
               {'role': 'tutor', 'text': 'Lyon was the Roman-era capital.'}]
    _ask(client, card, 'When did that change?', history)
    assert 'Lyon was the Roman-era capital.' in tutor.prompts[0]


def test_three_questions_per_card_is_the_limit(client, user, notebook, tutor):
    card = _card(user, notebook)
    three = [{'role': 'user', 'text': f'q{i}'} for i in range(3)]
    res = _ask(client, card, 'one more?', three)
    assert res.status_code == 400
    assert tutor.prompts == []


def test_a_blank_question_is_refused(client, user, notebook, tutor):
    card = _card(user, notebook)
    assert _ask(client, card, '   ').status_code == 400
    assert tutor.prompts == []


def test_a_card_with_no_source_still_gets_a_careful_answer(client, user, notebook, tutor):
    card = Flashcard.objects.create(user=user, question='Q', answer='A')
    res = _ask(client, card, 'Why?')
    assert res.status_code == 200
    assert 'No passage' in tutor.prompts[0] or 'no passage' in tutor.prompts[0]


def test_without_a_provider_it_says_so(client, user, notebook):
    card = _card(user, notebook)
    assert _ask(client, card, 'Why?').status_code == 503


def test_someone_elses_card_is_not_found(client, other_user, tutor):
    card = Flashcard.objects.create(user=other_user, question='Q', answer='A', is_public=True)
    assert _ask(client, card, 'Why?').status_code == 404
    assert tutor.prompts == []


def test_an_on_topic_question_beyond_the_passage_is_answered_and_marked(client, user, notebook, monkeypatch):
    """The passage is about why Paris; a student asks what the card's topic
    leads to next. Answered from general knowledge, marked so (2026-11-25)."""
    class General(Tutor):
        def generate_json(self, prompt):
            Tutor.prompts.append(prompt)
            return {'answer': 'France is a unitary state; Paris holds the government.', 'from': 'general'}
    Tutor.prompts = []
    monkeypatch.setattr('flashcards.services.tutor.get_ai_provider', lambda: General())
    card = _card(user, notebook)

    res = _ask(client, card, 'How is France governed from Paris?')

    assert res.json() == {'answer': 'France is a unitary state; Paris holds the government.', 'from': 'general'}
    prompt = Tutor.prompts[0]
    assert "about this card's topic" in prompt and 'not about this card' in prompt   # on topic, or turned away


def test_an_answer_from_the_passage_says_so(client, user, notebook, tutor):
    assert _ask(client, _card(user, notebook), 'Why not Lyon?').json()['from'] == 'passage'
