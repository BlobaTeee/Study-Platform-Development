"""'Why?' on a wrong answer: a short, source-grounded explanation."""
import pytest
from django.utils import timezone

from quizzes.models import MockTest, MockTestQuestion

pytestmark = pytest.mark.django_db


def _sat(user, notebook, **row):
    test = MockTest.objects.create(user=user, notebook=notebook, question_count=1, duration_minutes=5,
                                   completed_at=timezone.now(), score=0)
    defaults = dict(order=0, question_text='Capital of France?', options=['Paris', 'Rome', 'Oslo', 'Bern'],
                    correct_answer='Paris', user_answer='Rome', is_correct=False,
                    source_excerpt='Paris has been the capital of France since 508, when Clovis I chose it.')
    defaults.update(row)
    return test, MockTestQuestion.objects.create(mock_test=test, **defaults)


class Explainer:
    name = 'stub'
    prompts: list = []

    def generate_json(self, prompt):
        Explainer.prompts.append(prompt)
        return {'explanation': 'Clovis I made Paris the capital in 508; Rome is Italy\'s.'}


@pytest.fixture
def provider(monkeypatch):
    Explainer.prompts = []
    monkeypatch.setattr('quizzes.services.explain.get_ai_provider', lambda: Explainer())
    return Explainer


def test_a_wrong_answer_gets_an_explanation_grounded_in_the_excerpt(client, user, notebook, provider):
    test, row = _sat(user, notebook)

    res = client.post(f'/api/quizzes/mock-tests/{test.id}/explain/', {'paper_question_id': row.id}, format='json')

    assert res.status_code == 200
    assert res.json()['explanation'].startswith('Clovis I')
    prompt = provider.prompts[0]
    assert 'since 508' in prompt and 'Rome' in prompt and 'Paris' in prompt


def test_the_explanation_is_kept_so_a_second_look_costs_nothing(client, user, notebook, provider):
    test, row = _sat(user, notebook)
    client.post(f'/api/quizzes/mock-tests/{test.id}/explain/', {'paper_question_id': row.id}, format='json')
    client.post(f'/api/quizzes/mock-tests/{test.id}/explain/', {'paper_question_id': row.id}, format='json')
    assert len(provider.prompts) == 1
    row.refresh_from_db()
    assert row.ai_explanation.startswith('Clovis I')
    review = client.post(f'/api/quizzes/mock-tests/{test.id}/submit/').json()
    assert review['paper'][0]['ai_explanation'].startswith('Clovis I')


def test_a_right_answer_needs_no_explaining(client, user, notebook, provider):
    test, row = _sat(user, notebook, user_answer='Paris', is_correct=True)
    res = client.post(f'/api/quizzes/mock-tests/{test.id}/explain/', {'paper_question_id': row.id}, format='json')
    assert res.status_code == 400
    assert provider.prompts == []


def test_an_unsubmitted_paper_cannot_be_explained(client, user, notebook, provider):
    test, row = _sat(user, notebook)
    test.completed_at = None
    test.save(update_fields=['completed_at'])
    res = client.post(f'/api/quizzes/mock-tests/{test.id}/explain/', {'paper_question_id': row.id}, format='json')
    assert res.status_code == 400


def test_without_a_provider_it_says_so(client, user, notebook):
    test, row = _sat(user, notebook)
    res = client.post(f'/api/quizzes/mock-tests/{test.id}/explain/', {'paper_question_id': row.id}, format='json')
    assert res.status_code == 503


def test_someone_elses_paper_is_not_found(client, other_user, notebook):
    from notebooks.models import Notebook
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    test, row = _sat(other_user, theirs)
    res = client.post(f'/api/quizzes/mock-tests/{test.id}/explain/', {'paper_question_id': row.id}, format='json')
    assert res.status_code == 404
