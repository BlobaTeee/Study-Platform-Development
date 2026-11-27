"""A paper the student brings to the mock-test page, sat whole (2026-11-26).

Read once, sat as printed. The paper's own key marks it, so a Word file with
a key needs no further request; a photo's answers are found in one request;
only a written question gets a rubric. What is missed stays with the
paper's review: mock tests and practice no longer feed each other.
"""
import pytest

from exercises.models import Exercise
from quizzes.models import MockTest

pytestmark = pytest.mark.django_db
URL = '/api/exercises/papers/'
RUBRIC = {'complete': True, 'kind': 'written', 'difficulty': 'medium', 'format': 'steps',
          'solution': ['Bước một.', 'Bước hai.'],
          'checkpoints': [{'text': 'Nêu đúng quy tắc', 'basis': ''}, {'text': 'Ra đúng kết quả', 'basis': ''}],
          'mistakes': []}

CHOICE = {'label': 'Phần I · Câu 1', 'kind': 'choice', 'text': 'Kim loại nào khử mạnh nhất?',
          'options': [{'label': 'A', 'text': 'Na'}, {'label': 'B', 'text': 'K'}]}
TF = {'label': 'Phần II · Câu 1', 'kind': 'true_false', 'text': 'Cho pin Zn – Cu.',
      'statements': [{'label': 'a', 'text': 'Zn bị oxi hoá.'}, {'label': 'b', 'text': 'Cu là cực âm.'}]}
SHORT = {'label': 'Phần III · Câu 1', 'kind': 'short', 'text': 'Tính giá trị.'}
WRITTEN = {'label': 'Câu 4', 'kind': 'written', 'text': 'Giải thích vì sao sắt bị gỉ.'}


class Scripted:
    name = 'stub'

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def generate_json_from_images(self, prompt, images):
        return self.generate_json(prompt)


@pytest.fixture
def model(monkeypatch):
    def use(*replies):
        provider = Scripted(*replies)
        monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: provider)
        return provider
    return use


def test_a_word_paper_with_its_key_is_sat_without_asking_for_answers(client, model):
    provider = model({'problems': [RUBRIC]})                      # the written one's rubric only
    body = client.post(URL, {'title': 'Đề Hoá HK1', 'questions': [
        {**CHOICE, 'answer': 'b'}, {**TF, 'answer': {'a': True, 'b': False}}, {**SHORT, 'answer': '-0,7'},
        WRITTEN]}, format='json').json()
    assert [r['section'] for r in body['paper']] == ['choice', 'true_false', 'short', 'written']
    assert (body['template'], body['notebook_title'], body['dropped']) == ('paper', 'Đề Hoá HK1', [])
    assert round(sum(r['points'] for r in body['paper']), 2) == 10
    assert body['paper'][0]['options'] == ['A. Na', 'B. K']
    assert len(provider.prompts) == 1                              # no request for the keyed ones


def test_a_photos_answers_are_found_in_one_request(client, model):
    provider = model({'answers': [{'n': 1, 'answer': 'B'}, {'n': 2, 'answer': {'a': True, 'b': False}},
                                  {'n': 3, 'answer': '-0,7'}]})
    body = client.post(URL, {'title': 'Ảnh đề', 'questions': [{**CHOICE, 'hint': 'A'}, TF, SHORT]},
                       format='json').json()
    assert len(provider.prompts) == 1
    assert 'may be misread' in provider.prompts[0]                 # the photo's key only as a hint
    test = MockTest.objects.get(id=body['id'])
    assert [r.correct_answer for r in test.paper.order_by('order')][::2] == ['B. K', '-0,7']


def test_a_question_whose_answer_is_not_found_is_left_out(client, model):
    model({'answers': [{'n': 1, 'answer': 'B'}, {'n': 2, 'answer': 'Z'}]})
    body = client.post(URL, {'title': 'Ảnh đề', 'questions': [CHOICE, {**CHOICE, 'label': 'Câu 2'}]},
                       format='json').json()
    assert body['dropped'] == ['Câu 2'] and len(body['paper']) == 1


def test_what_is_missed_stays_with_the_paper(client, model):
    model()                                                        # all keyed: no request
    body = client.post(URL, {'title': 'Đề Hoá HK1', 'questions': [
        {**CHOICE, 'answer': 'B'}, {**SHORT, 'answer': '4'}]}, format='json').json()
    rows = {r['section']: r['id'] for r in body['paper']}
    url = f"/api/quizzes/mock-tests/{body['id']}"
    client.post(f'{url}/answer/', {'paper_question_id': rows['choice'], 'answer': 'A. Na'}, format='json')
    client.post(f'{url}/answer/', {'paper_question_id': rows['short'], 'answer': '4'}, format='json')

    review = client.post(f'{url}/submit/').json()

    assert review['mistake_count'] == 1
    assert not Exercise.objects.exists()                           # nothing sent to practice


def test_a_papers_words_are_shown_as_printed(client, model):
    """No tidying of the paper's own text: "Zn – Cu" stays a dash."""
    model()
    body = client.post(URL, {'title': 'Đề', 'questions': [
        {**SHORT, 'text': 'Cho pin điện hoá Zn – Cu.', 'answer': '1'},
        {**SHORT, 'label': 'Câu 2', 'text': 'Câu 2 — tính.', 'answer': '2'}]}, format='json').json()
    assert [r['question_text'] for r in body['paper']] == ['Cho pin điện hoá Zn – Cu.', 'Câu 2 — tính.']


def test_a_missed_question_still_waiting_gets_its_solution_when_opened(client, user, model):
    model({'problems': [{**RUBRIC, 'kind': 'short', 'answer': '4'}]})
    ex = Exercise.objects.create(user=user, notebook=None, origin='own', set_key='k' * 32, set_title='Đề',
                                 prompt='Tính giá trị.', status='revisit',
                                 reference={'kind': 'short', 'answer': '4', 'accept': [], 'pending': True})
    client.get(f'/api/exercises/{ex.id}/')
    ex.refresh_from_db()
    assert ex.reference['solution'] and ex.reference['answer'] == '4' and 'pending' not in ex.reference
