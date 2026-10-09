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


@pytest.mark.parametrize('raw, expected', [
    # The student never sees an "excerpt": writing about it is the model
    # describing its own input instead of the subject.
    ('The text states the tone is calm and matter-of-fact.', 'The tone is calm and matter-of-fact.'),
    ('The excerpt explains that institutional interfaces feel othering.',
     'Institutional interfaces feel othering.'),
    ('According to the excerpt, mitochondria make ATP.', 'Mitochondria make ATP.'),
    ('According to the passage, cells divide.', 'Cells divide.'),
    ('As the text explains, bonds store energy.', 'Bonds store energy.'),
    ('Theo đoạn trích, ty thể tạo ra ATP.', 'Ty thể tạo ra ATP.'),
    ('Đoạn văn cho biết ty thể tạo ra ATP.', 'Ty thể tạo ra ATP.'),
])
def test_talk_about_the_excerpt_is_removed(raw, expected):
    assert tidy_prose(raw) == expected


@pytest.mark.parametrize('raw, expected', [
    # Shapes measured in the stored mock-test explanations.
    ('The excerpt explicitly mentions that mobile phones sustain relationships.',
     'Mobile phones sustain relationships.'),
    ('The text explicitly states the tone is calm.', 'The tone is calm.'),
    ('The text specifies that filters cover day and distance.', 'Filters cover day and distance.'),
    ('The excerpt highlights that tone is a design variable.', 'Tone is a design variable.'),
    ("The excerpt states, 'mobile phones are a lifeline.'", 'Mobile phones are a lifeline.'),
    ('The document states: “Interaction design shapes behaviour.”', 'Interaction design shapes behaviour.'),
    ('The first sentence of the excerpt states the app is calm.', 'The app is calm.'),
])
def test_more_ways_of_talking_about_the_excerpt_are_removed(raw, expected):
    assert tidy_prose(raw) == expected


@pytest.mark.parametrize('raw, expected', [
    # A verb that takes an object cannot lose its subject; the document's own
    # name stands in, which is what the sentence is about.
    ('The text explicitly lists depleted batteries as a risk.', 'CityHelp lists depleted batteries as a risk.'),
    ('The excerpt identifies day filters as a feature.', 'CityHelp identifies day filters as a feature.'),
    ('The excerpt mentions the free meal locator.', 'CityHelp mentions the free meal locator.'),
])
def test_an_object_verb_keeps_the_sentence_with_the_documents_name(raw, expected):
    assert tidy_prose(raw, source_title='CityHelp') == expected


@pytest.mark.parametrize('raw, expected', [
    ('The excerpt explicitly links self-driving cars to accountability.', 'The reading links self-driving cars to accountability.'),
    ('The excerpt explicitly cites the IxDA definition of a conceptual model.', 'The reading cites the IxDA definition of a conceptual model.'),
])
def test_with_no_document_name_the_reading_stands_in(raw, expected):
    assert tidy_prose(raw, source_title='The reading') == expected


def test_an_apostrophe_inside_a_quote_does_not_end_it():
    raw = "The excerpt states, 'A device\u2019s value cannot be assessed in isolation.'"
    assert tidy_prose(raw) == 'A device\u2019s value cannot be assessed in isolation.'


def test_any_verb_after_the_excerpt_takes_the_documents_name():
    raw = "The excerpt prioritizes features that let users take direct action."
    assert tidy_prose(raw, source_title='CityHelp') == 'CityHelp prioritizes features that let users take direct action.'


def test_the_excerpt_inside_a_sentence_becomes_the_documents_name():
    raw = 'Mobile phones are a lifeline. The other options are not mentioned in the text.'
    assert tidy_prose(raw, source_title='CityHelp') == \
        'Mobile phones are a lifeline. The other options are not mentioned in CityHelp.'


def test_a_question_without_its_own_source_is_named_by_its_quiz(user, notebook):
    from notebooks.services.writing_style import _title_of
    from quizzes.models import Quiz
    source = notebook.sources.first()
    quiz = Quiz.objects.create(user=user, title='q', is_published=True)
    quiz.sources.set([source])
    q = Question.objects.create(quiz=quiz, question_text='Q?', question_type='multiple_choice',
                                options=['a', 'b'], correct_answer='a', order=0)
    assert _title_of(q) == source.title


def test_review_explanations_are_served_without_the_excerpt(client, user, notebook):
    from django.utils import timezone
    from quizzes.models import MockTest, MockTestQuestion
    source = notebook.sources.first()
    test = MockTest.objects.create(user=user, notebook=notebook, question_count=1, duration_minutes=5,
                                   completed_at=timezone.now(), score=0)
    MockTestQuestion.objects.create(
        mock_test=test, order=0, question_text='What do phones sustain?', options=['Ties', 'Jobs'],
        correct_answer='Ties', user_answer='Jobs', is_correct=False, source=source,
        explanation='The excerpt explicitly lists relationships as what phones sustain.')

    # A submitted paper answers a second submit with its review.
    row = client.post(f'/api/quizzes/mock-tests/{test.id}/submit/', {}, format='json').json()['paper'][0]

    assert row['explanation'] == f'{source.title} lists relationships as what phones sustain.'


@pytest.mark.parametrize('text', [
    # Cutting "The text lists" would leave a fragment ("Theft, loss ... as
    # factors."): these verbs take an object, not a clause, so the sentence
    # is left as written.
    'The text lists theft, loss and damage as factors that undermine safety.',
    'The excerpt describes a calm, matter-of-fact tone.',
    'The passage mentions three meal locations.',
])
def test_a_sentence_that_would_be_left_a_fragment_is_kept(text):
    # Without the document's name there is nothing to stand in for it.
    assert tidy_prose(text) == text


@pytest.mark.parametrize('raw, expected', [
    ('What is the primary focus of Interaction Design according to the provided text?',
     'What is the primary focus of Interaction Design?'),
    ('According to the tutorial document, which component is NOT required?', 'Which component is NOT required?'),
    ('What is a key finding of the article regarding AI in education?', 'What is a key finding regarding AI in education?'),
    # A real, named source stays: it says where a claim comes from.
    ('According to usability.gov, what is the focus of Interaction Design?',
     'According to usability.gov, what is the focus of Interaction Design?'),
])
def test_more_question_shapes(raw, expected):
    from notebooks.services.writing_style import tidy_question
    assert tidy_question(raw) == expected


@pytest.mark.parametrize('raw, expected', [
    ('What is the third requirement for CityHelp based on the excerpt?', 'What is the third requirement for CityHelp?'),
    ('According to the excerpt, how should good design treat dignity?', 'How should good design treat dignity?'),
    ('Which element is mentioned in the text as a mobile pattern?', 'Which element is a mobile pattern?'),
    ('Theo đoạn trích, ty thể tạo ra gì?', 'Ty thể tạo ra gì?'),
    ('What do mitochondria make?', 'What do mitochondria make?'),
])
def test_questions_do_not_mention_the_excerpt(raw, expected):
    from notebooks.services.writing_style import tidy_question
    assert tidy_question(raw) == expected


def test_the_guide_shows_an_example_and_bans_talk_about_the_excerpt():
    assert 'Instead of' in WRITING_STYLE
    assert 'excerpt' in WRITING_STYLE and 'ensure' in WRITING_STYLE


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


# ---- what is already stored ----------------------------------------------------

def test_stored_cards_and_questions_are_served_clean(client, user, notebook):
    # Written before the cleanup existed: shown clean, left as stored.
    card = Flashcard.objects.create(user=user, notebook=notebook, question='What is the tone based on the excerpt?',
                                    answer='Calm', explanation='The text states the tone is calm — and plain.')
    from quizzes.models import Quiz
    quiz = Quiz.objects.create(user=user, title='q', is_published=True)
    q = Question.objects.create(quiz=quiz, question_text='According to the excerpt, what is the tone?',
                                question_type='multiple_choice', options=['Calm', 'Loud'], correct_answer='Calm',
                                explanation='The excerpt explains that the tone is calm.', order=0)

    listed = client.get('/api/flashcards/flashcards/').json()
    listed = listed.get('results', listed) if isinstance(listed, dict) else listed
    served = client.get(f'/api/quizzes/quizzes/{quiz.id}/').json()['questions'][0]

    assert listed[0]['question'] == 'What is the tone?'
    assert listed[0]['explanation'] == 'The tone is calm, and plain.'
    assert served['question_text'] == 'What is the tone?'
    assert served['explanation'] == 'The tone is calm.'
    card.refresh_from_db(); q.refresh_from_db()
    assert card.question.endswith('based on the excerpt?')
    assert q.question_text.startswith('According to')
