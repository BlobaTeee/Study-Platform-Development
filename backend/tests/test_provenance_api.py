"""A generated question remembers the passage it came from; a sitting
freezes it; the review hands it back so a wrong answer points at the
exact place to reread."""
import pytest

from notebooks.models import Notebook
from quizzes.models import MockTest, MockTestQuestion, Question, Quiz
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

CELLS = ' '.join(f'Cells sentence {i} about the mitochondrion and ATP.' for i in range(30))
GENES = ' '.join(f'Genetics sentence {i} about DNA and RNA.' for i in range(30))


class _EchoProvider:
    """Answers with a question whose text quotes the excerpt it was given, so
    the test can tell which chunk each question came from."""
    name = 'stub'
    def generate_json(self, prompt):
        excerpt = prompt.split('Excerpt:\n', 1)[1].strip()
        first = excerpt.split('.')[0]
        return {'questions': [{'question_text': f'About: {first}?', 'correct_answer': 'yes',
                               'distractors': ['no', 'maybe', 'never'], 'explanation': 'because'}]}
    def summarize(self, text, title=''):
        return ''


@pytest.fixture
def two_docs(user):
    nb = Notebook.objects.create(user=user, title='Bio')
    cells = make_source(nb, 'Cells', CELLS)
    genes = make_source(nb, 'Genetics', GENES)
    return nb, cells, genes


def test_generated_questions_carry_their_source_and_passage(client, two_docs, monkeypatch, settings):
    settings.RAG_CHUNKS = 4
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: _EchoProvider())
    nb, cells, genes = two_docs

    res = client.post(f'/api/notebooks/notebooks/{nb.id}/generate_quiz/',
                      {'source_ids': [cells.id, genes.id], 'question_count': 4}, format='json')

    assert res.status_code == 201, res.json()
    questions = list(Question.objects.filter(quiz__user=nb.user))
    assert questions
    for q in questions:
        assert q.source_excerpt, q.question_text
        assert q.source_id in (cells.id, genes.id, None)
        if 'Cells sentence' in q.question_text:
            assert q.source_id == cells.id
        if 'Genetics sentence' in q.question_text:
            assert q.source_id == genes.id
    assert any(q.source_id is not None for q in questions)


def _quiz_with_provenance(user, notebook, source):
    quiz = Quiz.objects.create(user=user, title='q', is_published=True)
    quiz.sources.set([source])
    return [Question.objects.create(
        quiz=quiz, question_text=f'Q{i}?', question_type='multiple_choice',
        options=['a', 'b', 'c'], correct_answer='a', order=i,
        source=source, source_excerpt=f'Passage {i} of the document.') for i in range(5)]


def test_a_sitting_freezes_source_and_passage_and_the_review_returns_them(client, user, two_docs):
    nb, cells, _ = two_docs
    _quiz_with_provenance(user, nb, cells)

    started = client.post('/api/quizzes/mock-tests/', {'notebook': nb.id, 'question_count': 5,
                                                       'duration_minutes': 10}, format='json')
    assert started.status_code == 201, started.json()
    test_id = started.json()['id']
    frozen = MockTestQuestion.objects.filter(mock_test_id=test_id)
    assert all(row.source_id == cells.id and row.source_excerpt.startswith('Passage') for row in frozen)

    review = client.post(f'/api/quizzes/mock-tests/{test_id}/submit/', {}, format='json').json()
    row = review['paper'][0]
    assert row['source'] == {'id': cells.id, 'title': 'Cells', 'notebook': nb.id}
    assert row['source_excerpt'].startswith('Passage')


def test_the_review_survives_the_source_being_deleted(client, user, two_docs):
    nb, cells, _ = two_docs
    _quiz_with_provenance(user, nb, cells)
    test_id = client.post('/api/quizzes/mock-tests/', {'notebook': nb.id, 'question_count': 5,
                                                       'duration_minutes': 10}, format='json').json()['id']
    client.post(f'/api/quizzes/mock-tests/{test_id}/submit/', {}, format='json')

    cells.delete()

    row = client.post(f'/api/quizzes/mock-tests/{test_id}/submit/', {}, format='json').json()['paper'][0]
    assert row['source'] is None
    assert row['source_excerpt'].startswith('Passage')     # the passage outlives the file


def test_a_question_without_provenance_reviews_as_before(client, user, two_docs):
    nb, cells, _ = two_docs
    quiz = Quiz.objects.create(user=user, title='old', is_published=True); quiz.sources.set([cells])
    for i in range(5):
        Question.objects.create(quiz=quiz, question_text=f'Q{i}?', question_type='multiple_choice',
                                options=['a', 'b'], correct_answer='a', order=i)
    test_id = client.post('/api/quizzes/mock-tests/', {'notebook': nb.id, 'question_count': 5,
                                                       'duration_minutes': 10}, format='json').json()['id']
    row = client.post(f'/api/quizzes/mock-tests/{test_id}/submit/', {}, format='json').json()['paper'][0]
    assert row['source'] is None and row['source_excerpt'] == ''
