"""Your cards and questions, as a file you can open anywhere or import into Anki."""
import csv
import io

import pytest

from flashcards.models import Flashcard
from notebooks.models import Notebook
from quizzes.models import Question, Quiz

pytestmark = pytest.mark.django_db


def _rows(res):
    text = res.content.decode('utf-8-sig')            # BOM stripped
    return list(csv.reader(io.StringIO(text)))


def _card(user, notebook, q, a, archived=False):
    card = Flashcard.objects.create(user=user, notebook=notebook, question=q, answer=a, archived=archived)
    card.sources.set(notebook.sources.all())
    return card


def test_flashcards_export_is_a_utf8_csv_with_a_bom_for_excel(client, user, notebook):
    _card(user, notebook, 'Quang hợp là gì?', 'Quá trình tạo đường từ CO₂ và nước.')

    res = client.get(f'/api/notebooks/notebooks/{notebook.id}/export/?kind=flashcards')

    assert res.status_code == 200
    assert res['Content-Type'].startswith('text/csv')
    assert res['Content-Disposition'].startswith('attachment; filename=')
    assert res.content.startswith(b'\xef\xbb\xbf')
    rows = _rows(res)
    assert rows[0] == ['front', 'back', 'source']
    assert rows[1][:2] == ['Quang hợp là gì?', 'Quá trình tạo đường từ CO₂ và nước.']
    assert rows[1][2] == ' / '.join(s.title for s in notebook.sources.all())   # every source the card came from


def test_archived_cards_are_not_exported(client, user, notebook):
    _card(user, notebook, 'live', 'a')
    _card(user, notebook, 'old', 'b', archived=True)
    rows = _rows(client.get(f'/api/notebooks/notebooks/{notebook.id}/export/?kind=flashcards'))
    assert [r[0] for r in rows[1:]] == ['live']


def test_questions_export_has_one_column_per_option(client, user, notebook):
    quiz = Quiz.objects.create(user=user, title='Q', is_published=True)
    quiz.sources.set(notebook.sources.all())
    Question.objects.create(quiz=quiz, question_text='Capital of France?', question_type='multiple_choice',
                            options=['Paris', 'Rome', 'Oslo', 'Bern'], correct_answer='Paris',
                            explanation='Since 508.', source=notebook.sources.first())

    rows = _rows(client.get(f'/api/notebooks/notebooks/{notebook.id}/export/?kind=questions'))

    assert rows[0] == ['question', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer', 'explanation', 'source']
    assert rows[1] == ['Capital of France?', 'Paris', 'Rome', 'Oslo', 'Bern', 'Paris', 'Since 508.',
                       notebook.sources.first().title]


def test_retired_quizzes_are_not_exported(client, user, notebook):
    quiz = Quiz.objects.create(user=user, title='Old', is_published=False)
    quiz.sources.set(notebook.sources.all())
    Question.objects.create(quiz=quiz, question_text='gone?', question_type='multiple_choice',
                            options=['a', 'b'], correct_answer='a')
    rows = _rows(client.get(f'/api/notebooks/notebooks/{notebook.id}/export/?kind=questions'))
    assert len(rows) == 1


def test_an_unknown_kind_is_refused(client, notebook):
    assert client.get(f'/api/notebooks/notebooks/{notebook.id}/export/?kind=everything').status_code == 400


def test_someone_elses_notebook_is_not_found(client, other_user):
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    assert client.get(f'/api/notebooks/notebooks/{theirs.id}/export/?kind=flashcards').status_code == 404
