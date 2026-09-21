"""Weak concepts: what a student keeps missing, and a paper to practise it."""
import pytest
from django.utils import timezone

from quizzes.models import MockTest, MockTestQuestion, Question, Quiz

pytestmark = pytest.mark.django_db

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


def _missed(user, notebook, pairs, source=None):
    quiz = Quiz.objects.create(user=user, title='Pool', is_published=True)
    quiz.sources.set(notebook.sources.all())
    qs = [Question.objects.create(quiz=quiz, question_text=q, question_type='multiple_choice',
                                  options=[a, 'x', 'y', 'z'], correct_answer=a, order=i,
                                  source=source, source_excerpt='')
          for i, (q, a) in enumerate(pairs)]
    test = MockTest.objects.create(user=user, notebook=notebook, question_count=len(qs),
                                   duration_minutes=5, completed_at=timezone.now(), score=0)
    for i, q in enumerate(qs):
        MockTestQuestion.objects.create(mock_test=test, question=q, order=i, question_text=q.question_text,
                                        options=q.options, correct_answer=q.correct_answer,
                                        user_answer='x', is_correct=False)
    return qs


def _concepts(client, notebook):
    return client.get(f'/api/quizzes/weak-concepts/?notebook={notebook.id}').json()['concepts']


# ---- GET weak-concepts ------------------------------------------------------------

def test_missed_questions_are_grouped_by_concept_biggest_first(client, user, notebook):
    phones = _missed(user, notebook, PHONES)
    cars = _missed(user, notebook, CARS)
    _missed(user, notebook, LONE)

    concepts = _concepts(client, notebook)

    assert [c['count'] for c in concepts] == [3, 2]
    assert set(concepts[0]['question_ids']) == {q.id for q in phones}
    assert set(concepts[1]['question_ids']) == {q.id for q in cars}
    assert concepts[0]['label'] and 'correct_answer' not in concepts[0]


def test_without_a_provider_the_label_is_the_clusters_key_terms(client, user, notebook):
    _missed(user, notebook, PHONES)
    _missed(user, notebook, CARS)
    label = _concepts(client, notebook)[0]['label'].lower()
    assert any(w in label for w in ('phone', 'mobile', 'homeless'))


def test_a_provider_names_the_concept(client, user, notebook, monkeypatch):
    class Namer:
        name = 'stub'
        def generate_json(self, prompt):
            return {'label': 'Phones and homeless youth'}
    monkeypatch.setattr('quizzes.services.concepts.get_ai_provider', lambda: Namer())
    _missed(user, notebook, PHONES)
    _missed(user, notebook, CARS)
    assert _concepts(client, notebook)[0]['label'] == 'Phones and homeless youth'


def test_a_lone_miss_is_not_a_concept_yet(client, user, notebook):
    _missed(user, notebook, LONE)
    assert _concepts(client, notebook) == []


def test_someone_elses_notebook_is_not_found(client, other_user):
    from notebooks.models import Notebook
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    assert client.get(f'/api/quizzes/weak-concepts/?notebook={theirs.id}').status_code == 404


# ---- POST weak-concepts/practice ---------------------------------------------------

class _Writer:
    """A provider that writes five new questions about whatever it is asked."""
    name = 'stub'
    prompts: list[str] = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return {'questions': [
            {'question_text': f'New question {i} about the concept?', 'correct_answer': 'right',
             'distractors': ['wrong 1', 'wrong 2', 'wrong 3'], 'explanation': 'because'}
            for i in range(5)]}


def test_reworded_misses_are_filtered_out_of_a_practice_paper():
    from quizzes.services.practice import novel_questions
    missed = ['What role do mobile phones play in the personal safety of homeless young people?',
              'Why is the safety benefit of phones undermined?']
    generated = [
        {'question_text': 'What role do mobile phones play in the personal safety of homeless young people?'},
        {'question_text': 'What role do mobile phones play in personal safety for homeless youth?'},
        {'question_text': 'Which everyday events erode the protection a phone offers?'},
        {'question_text': 'Why does CityHelp put one-tap emergency buttons first?'},
    ]
    kept = novel_questions(generated, missed)
    assert [g['question_text'][:5] for g in kept] == ['Which', 'Why d']


def test_a_model_that_only_parrots_the_misses_gets_one_more_try(client, user, notebook, monkeypatch):
    class Parrot:
        name = 'stub'
        calls = 0
        def generate_json(self, prompt):
            Parrot.calls += 1
            if Parrot.calls == 1:
                return {'questions': [{'question_text': q, 'correct_answer': a,
                                       'distractors': ['x', 'y', 'z']} for q, a in PHONES]}
            return {'questions': [{'question_text': 'Which events erode the protection a phone offers?',
                                   'correct_answer': 'theft', 'distractors': ['x', 'y', 'z']},
                                  {'question_text': 'Who is most exposed when a phone battery dies?',
                                   'correct_answer': 'youth', 'distractors': ['x', 'y', 'z']}]}
    monkeypatch.setattr('quizzes.services.practice.get_ai_provider', lambda: Parrot())
    phones = _missed(user, notebook, PHONES)

    res = _practice(client, notebook, [q.id for q in phones])

    assert res.status_code == 201
    assert Parrot.calls == 2
    assert res.json()['question_count'] == 2


def _practice(client, notebook, ids, label='Phones'):
    return client.post('/api/quizzes/weak-concepts/practice/',
                       {'notebook': notebook.id, 'question_ids': ids, 'label': label}, format='json')


def test_practice_makes_a_fresh_quiz_on_the_concept(client, user, notebook, monkeypatch):
    writer = _Writer(); writer.prompts = []
    monkeypatch.setattr('quizzes.services.practice.get_ai_provider', lambda: writer)
    phones = _missed(user, notebook, PHONES, source=notebook.sources.first())

    res = _practice(client, notebook, [q.id for q in phones])

    assert res.status_code == 201, res.json()
    quiz = Quiz.objects.get(id=res.json()['quiz_id'])
    assert quiz.is_published and quiz.title == 'Practice: Phones'
    assert set(quiz.sources.values_list('id', flat=True)) == {notebook.sources.first().id}
    assert quiz.questions.count() == 5
    assert res.json()['source_ids'] == [notebook.sources.first().id]
    # The model is told what was missed, and given the passage to write from.
    assert PHONES[0][0] in writer.prompts[0]
    assert 'Sentence number' in writer.prompts[0]


def test_practice_does_not_retire_the_students_other_quizzes(client, user, notebook, monkeypatch):
    monkeypatch.setattr('quizzes.services.practice.get_ai_provider', lambda: _Writer())
    phones = _missed(user, notebook, PHONES)
    _practice(client, notebook, [q.id for q in phones])
    assert Quiz.objects.filter(user=user, title='Pool', is_published=True).exists()


def test_practice_without_a_provider_says_so(client, user, notebook):
    phones = _missed(user, notebook, PHONES)
    res = _practice(client, notebook, [q.id for q in phones])
    assert res.status_code == 503
    assert Quiz.objects.filter(title__startswith='Practice').count() == 0


def test_practice_only_accepts_the_students_own_questions(client, user, other_user, notebook, monkeypatch):
    monkeypatch.setattr('quizzes.services.practice.get_ai_provider', lambda: _Writer())
    from notebooks.models import Notebook
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    from tests.conftest import make_source
    make_source(theirs, 'X')
    their_q = _missed(other_user, theirs, PHONES)
    res = _practice(client, notebook, [q.id for q in their_q])
    assert res.status_code == 400
