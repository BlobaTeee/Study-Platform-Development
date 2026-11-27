"""Typing a missing word: moved from flashcards to quizzes (2026-11-26).

A new deck is question-and-answer only. A quiz mixes in a few blanks: one
sentence from the document with a key term hidden, typed in, and marked
right when the word is right or only off by an accent or one slip. Live
rounds and mock tests need options to choose from, so they leave blanks out.
"""
import pytest

from flashcards.models import Flashcard
from quizzes.models import Question, Quiz, QuizAttempt
from quizzes.services.paper import typed_verdict

pytestmark = pytest.mark.django_db

CLOZE = {'kind': 'cloze',
         'question': 'Usability goals measure whether a product is _____, safe and easy to learn.',
         'answer': 'effective', 'explanation': 'x', 'difficulty': 'easy'}
BASIC = {'question': 'What do UX goals describe?', 'answer': 'How the experience feels',
         'explanation': 'x', 'difficulty': 'medium'}
BLANK_Q = {'kind': 'fill_blank', 'question_text': 'Usability goals measure whether a product is _____, safe and easy.',
           'correct_answer': 'effective', 'explanation': 'x'}
CHOICE_Q = {'kind': 'multiple_choice', 'question_text': 'What do UX goals describe?',
            'correct_answer': 'How it feels', 'distractors': ['Its price', 'Its size', 'Its code'], 'explanation': 'x'}


class _Provider:
    name = 'stub'

    def __init__(self, key, items):
        self.key, self.items, self.prompts = key, items, []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return {self.key: self.items}

    def summarize(self, text, title=''):
        return ''


def _use(monkeypatch, key, items):
    provider = _Provider(key, items)
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)
    return provider


def _ids(notebook):
    return list(notebook.sources.values_list('id', flat=True))


def test_a_new_deck_has_no_blanks_to_type(client, notebook, monkeypatch):
    provider = _use(monkeypatch, 'flashcards', [CLOZE, BASIC])
    res = client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_flashcards/',
                      {'source_ids': _ids(notebook), 'count': 5}, format='json')
    assert res.status_code == 201
    assert 'cloze' not in provider.prompts[-1]
    assert set(Flashcard.objects.values_list('kind', flat=True)) == {'basic'}


def test_a_quiz_asks_for_some_blanks_and_keeps_a_sound_one(client, notebook, monkeypatch):
    provider = _use(monkeypatch, 'questions', [BLANK_Q, CHOICE_Q] * 3)
    res = client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_quiz/',
                      {'source_ids': _ids(notebook), 'question_count': 4}, format='json')
    assert res.status_code == 201, res.json()
    assert '"kind": "fill_blank"' in provider.prompts[0]
    blank = Question.objects.filter(question_type='fill_blank').first()
    assert blank.question_text == 'Usability goals measure whether a product is ___, safe and easy.'
    assert (blank.options, blank.correct_answer) == ([], 'effective')
    assert Question.objects.filter(question_type='multiple_choice').exists()


@pytest.mark.parametrize('broken', [
    {**BLANK_Q, 'question_text': 'Usability goals measure whether a product is effective.'},   # no blank
    {**BLANK_Q, 'question_text': 'Usability goals are ___, ___ and easy to learn.'},           # two blanks
    {**BLANK_Q, 'question_text': 'An effective product is ___, safe and easy to learn.'},      # answer visible
    {**BLANK_Q, 'correct_answer': 'effective in every one of the situations it is used in'},   # not a key term
])
def test_a_broken_blank_is_left_out(client, notebook, monkeypatch, broken):
    _use(monkeypatch, 'questions', [broken, CHOICE_Q])
    client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_quiz/',
                {'source_ids': _ids(notebook), 'question_count': 4}, format='json')
    assert not Question.objects.filter(question_type='fill_blank').exists()


@pytest.mark.parametrize('typed, verdict', [
    ('effective', 'correct'), ('  Effective. ', 'correct'), ('nhiệt độ', 'wrong'),
    ('effectiv', 'close'), ('', 'empty'), ('efficient', 'wrong'),
])
def test_a_typed_word_is_checked_like_the_page_shows(typed, verdict):
    assert typed_verdict(typed, 'effective') == verdict


def test_vietnamese_typed_without_accents_counts():
    assert typed_verdict('nhiet do', 'nhiệt độ') == 'close'
    assert typed_verdict('đường', 'duong') == 'close'


def _blank_quiz(user, notebook):
    quiz = Quiz.objects.create(user=user, title='Q', is_published=True)
    quiz.sources.set(_ids(notebook))
    q = Question.objects.create(quiz=quiz, question_text='A product is ___, safe.', question_type='fill_blank',
                                options=[], correct_answer='hiệu quả')
    return quiz, q


def test_a_typed_answer_off_by_accents_is_marked_right(client, user, notebook):
    quiz, q = _blank_quiz(user, notebook)
    attempt = QuizAttempt.objects.create(user=user, quiz=quiz)
    right = client.post(f'/api/quizzes/attempts/{attempt.id}/submit_answer/',
                        {'question_id': q.id, 'answer': 'hieu qua'}, format='json').json()
    wrong = client.post(f'/api/quizzes/attempts/{attempt.id}/submit_answer/',
                        {'question_id': q.id, 'answer': 'an toàn'}, format='json').json()
    assert right['is_correct'] is True and wrong['is_correct'] is False


def test_blanks_stay_out_of_mock_tests(user, notebook):
    from quizzes.views import _question_pool
    _blank_quiz(user, notebook)
    assert _question_pool(user, _ids(notebook)) == []


def test_an_old_cloze_card_is_still_served(client, user, notebook):
    Flashcard.objects.create(user=user, notebook=notebook, kind='cloze', question='A product is ___, safe.',
                             answer='effective')
    listed = client.get('/api/flashcards/flashcards/').json()
    listed = listed.get('results', listed) if isinstance(listed, dict) else listed
    assert listed[0]['kind'] == 'cloze'
