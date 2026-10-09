"""Văn bản AI viết trong app phải đọc như người viết.

Every prompt that asks for prose carries the same short style guide, and
what comes back is tidied of the tells a prompt does not always stop: dashes
used as all-purpose punctuation, and a chatbot's greeting or sign-off left
around the content.
"""
import pytest

from flashcards.models import Flashcard
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose
from quizzes.models import Question
from tests.conftest import make_source

pytestmark = pytest.mark.django_db


# ---- the tidy step ----------------------------------------------------------------

@pytest.mark.parametrize('raw, expected', [
    ('The policy — announced without warning — affects workers.',
     'The policy, announced without warning, affects workers.'),
    ('Usability goals – efficiency and safety – come first.',
     'Usability goals, efficiency and safety, come first.'),
    ('Bonds break -- and new ones form.', 'Bonds break, and new ones form.'),
    ('Write a 3–5 sentence overview.', 'Write a 3-5 sentence overview.'),
    ('Great question! Mitochondria make ATP.', 'Mitochondria make ATP.'),
    ('Certainly. Mitochondria make ATP.', 'Mitochondria make ATP.'),
    ('Mitochondria make ATP. I hope this helps!', 'Mitochondria make ATP.'),
    ("Mitochondria make ATP. Let me know if you'd like more detail.", 'Mitochondria make ATP.'),
    ('Câu hỏi hay! Ty thể tạo ra ATP.', 'Ty thể tạo ra ATP.'),
    ('Ty thể tạo ra ATP. Hy vọng điều này giúp ích cho bạn!', 'Ty thể tạo ra ATP.'),
    ('Mitochondria make ATP.', 'Mitochondria make ATP.'),
    ('', ''),
])
def test_tells_are_tidied_and_the_content_kept(raw, expected):
    assert tidy_prose(raw) == expected


def test_dashes_inside_words_and_code_are_left_alone():
    text = 'A well-known self-driving car uses `rm -rf` and the URL https://a.b/x-y.'
    assert tidy_prose(text) == text


def test_a_reply_that_is_only_a_greeting_is_kept_rather_than_blanked():
    assert tidy_prose('Great question!') == 'Great question!'


# ---- prompts carry the guide ---------------------------------------------------

class _Capture:
    name = 'stub'

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return self.reply

    def summarize(self, text, title=''):
        return ''


def test_the_quiz_prompt_carries_the_guide():
    from notebooks.services.generate import quiz_prompt
    assert WRITING_STYLE in quiz_prompt('Cells divide.', 4, 'en', 'Biology')


def test_the_variant_prompt_carries_the_guide():
    from flashcards.services.variant_generator import build_variant_prompt
    assert WRITING_STYLE in build_variant_prompt('Q?', 'A', '')


def test_a_generated_deck_keeps_tidy_explanations(client, notebook, monkeypatch):
    provider = _Capture({'flashcards': [{
        'question': 'What do mitochondria make?', 'answer': 'ATP',
        'explanation': 'Great question! Mitochondria — the cell’s power plants — make ATP.'}]})
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)
    ids = list(notebook.sources.values_list('id', flat=True))

    client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_flashcards/',
                {'source_ids': ids, 'count': 3}, format='json')

    assert WRITING_STYLE in provider.prompts[-1]
    assert Flashcard.objects.get(question='What do mitochondria make?').explanation == \
        'Mitochondria, the cell’s power plants, make ATP.'


def test_a_generated_quiz_keeps_tidy_explanations(client, notebook, monkeypatch):
    provider = _Capture({'questions': [{
        'question_text': f'Which organelle makes ATP, case {i}?', 'correct_answer': 'Mitochondria',
        'distractors': ['Ribosome', 'Nucleus', 'Golgi body'],
        'explanation': 'Mitochondria — not ribosomes — make ATP. I hope this helps!'} for i in range(6)]})
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)
    ids = list(notebook.sources.values_list('id', flat=True))

    client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_quiz/',
                {'source_ids': ids, 'question_count': 4}, format='json')

    explanations = set(Question.objects.values_list('explanation', flat=True))
    assert explanations == {'Mitochondria, not ribosomes, make ATP.'}


def test_the_tutor_prompt_and_answer(user, notebook, monkeypatch):
    from flashcards.services.tutor import ask
    provider = _Capture({'answer': 'Certainly! ATP is made in the mitochondria — mostly.'})
    monkeypatch.setattr('flashcards.services.tutor.get_ai_provider', lambda: provider)
    card = Flashcard.objects.create(user=user, notebook=notebook, question='Q?', answer='A')

    answer = ask(card, 'Where is ATP made?', [])

    assert WRITING_STYLE in provider.prompts[-1]
    assert answer == 'ATP is made in the mitochondria, mostly.'


def test_feynman_feedback_is_tidy(client, user, notebook, monkeypatch):
    provider = _Capture({'correct': ['You named ATP — good.'], 'missing': ['The Krebs cycle – its role.'],
                         'wrong': [{'claim': 'Ribosomes make ATP.', 'correction': 'Mitochondria do — not ribosomes.'}],
                         'level': 'most', 'reread': []})
    monkeypatch.setattr('study_sessions.feynman.get_ai_provider', lambda: provider)
    source = make_source(notebook, 'Cells', 'Mitochondria make ATP through respiration. ' * 30)
    card = Flashcard.objects.create(user=user, notebook=notebook, question='Q?', answer='A')
    card.sources.set([source])

    body = client.post('/api/study/explain/', {'card_ids': [card.id], 'concept': 'ATP',
                                               'text': 'ATP comes from ribosomes in the cell.'}, format='json').json()

    assert WRITING_STYLE in provider.prompts[-1]
    assert body['correct'] == ['You named ATP, good.']
    assert body['missing'] == ['The Krebs cycle, its role.']
    assert body['wrong'][0]['correction'] == 'Mitochondria do, not ribosomes.'
