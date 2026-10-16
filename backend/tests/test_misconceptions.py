"""Chỗ hay nhầm: what the student keeps confusing, read from the wrong answers they chose.

A wrong answer says more than "wrong": the option picked is what the
student took the right answer to be. When the same mix-up shows in two or
more different questions, it is a misconception worth naming ("you mix up
usability goals with UX goals"), with contrast cards that set the two side
by side. One request per notebook finds them, and is asked again only when
the wrong answers change.
"""
import pytest
from django.utils import timezone

from flashcards.models import Flashcard
from notebooks.models import Notebook
from quizzes.models import MockTest, MockTestQuestion
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

URL = '/api/quizzes/misconceptions/'

WRONG = [
    ('Which is a usability goal?', 'Efficiency', 'Enjoyment'),
    ('Which goal is about how well a product works?', 'Being easy to learn', 'Being fun'),
    ('Which of these measures usability?', 'Time to complete a task', 'How satisfying it feels'),
    ('What is the intended tone of the app?', 'Calm and matter-of-fact', 'Urgent and demanding'),
]

FOUND = {'misconceptions': [{
    'confused': 'Usability goals', 'with': 'User experience goals',
    'difference': 'Usability goals are about how well a product works; UX goals are about how it feels.',
    'answers': [1, 2, 3],
    'cards': [{'question': 'Is "efficient to use" a usability goal or a UX goal?', 'answer': 'A usability goal'},
              {'question': 'Is "enjoyable" a usability goal or a UX goal?', 'answer': 'A UX goal'}],
}]}


class _Finder:
    name = 'stub'

    def __init__(self, reply=None, fail=False):
        self.reply = FOUND if reply is None else reply
        self.fail = fail
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError('down')
        return self.reply

    def summarize(self, text, title=''):
        return ''


@pytest.fixture
def finder(monkeypatch):
    f = _Finder()
    monkeypatch.setattr('quizzes.services.misconceptions.get_ai_provider', lambda: f)
    return f


def _sat(user, notebook, wrong=WRONG):
    source = notebook.sources.first()
    test = MockTest.objects.create(user=user, notebook=notebook, question_count=len(wrong),
                                   duration_minutes=10, completed_at=timezone.now(), score=0)
    for i, (q, right, chose) in enumerate(wrong):
        MockTestQuestion.objects.create(mock_test=test, order=i, question_text=q, correct_answer=right,
                                        options=[right, chose, 'x', 'y'], user_answer=chose,
                                        is_correct=False, source=source)
    return test


def _listed(client):
    res = client.get(URL)
    assert res.status_code == 200, res.content
    return res.json()['notebooks']


def test_a_mix_up_seen_in_several_questions_is_named(client, user, notebook, finder):
    _sat(user, notebook)

    listed = _listed(client)

    assert [nb['notebook_id'] for nb in listed] == [notebook.id]
    item = listed[0]['items'][0]
    assert item['confused'] == 'Usability goals' and item['with'] == 'User experience goals'
    assert item['difference'].startswith('Usability goals are about')
    assert item['evidence'] == 3
    assert 'Which is a usability goal?' in item['examples']
    # The prompt shows the student's actual choices: that is the evidence.
    assert 'Enjoyment' in finder.prompts[-1] and 'Efficiency' in finder.prompts[-1]


def test_a_mix_up_seen_once_is_not_a_misconception(client, user, notebook, finder):
    finder.reply = {'misconceptions': [dict(FOUND['misconceptions'][0], answers=[4])]}
    _sat(user, notebook)

    assert _listed(client) == []


def test_answers_the_model_made_up_are_not_evidence(client, user, notebook, finder):
    finder.reply = {'misconceptions': [dict(FOUND['misconceptions'][0], answers=[1, 99, 0])]}
    _sat(user, notebook)

    assert _listed(client) == []        # one real answer left: not enough


def test_too_few_wrong_answers_asks_nothing(client, user, notebook, finder):
    _sat(user, notebook, WRONG[:2])

    assert _listed(client) == []
    assert finder.prompts == []


def test_the_finding_is_kept_until_the_wrong_answers_change(client, user, notebook, finder):
    _sat(user, notebook)
    _listed(client)
    _listed(client)
    assert len(finder.prompts) == 1

    _sat(user, notebook, [('Which is a UX goal?', 'Being fun', 'Being efficient')])
    _listed(client)
    assert len(finder.prompts) == 2


def test_a_failed_request_is_tried_again_next_time(client, user, notebook, monkeypatch):
    monkeypatch.setattr('quizzes.services.misconceptions.get_ai_provider', lambda: _Finder(fail=True))
    _sat(user, notebook)
    assert _listed(client) == []

    f = _Finder()
    monkeypatch.setattr('quizzes.services.misconceptions.get_ai_provider', lambda: f)
    assert _listed(client)[0]['items']


def test_only_my_own_answers_count(client, other_client, user, notebook, finder):
    _sat(user, notebook)
    assert other_client.get(URL).json()['notebooks'] == []


def test_contrast_cards_are_made_once_and_opened(client, user, notebook, finder):
    _sat(user, notebook)
    key = _listed(client)[0]['items'][0]['key']

    first = client.post(f'{URL}practice/', {'notebook_id': notebook.id, 'key': key}, format='json')
    second = client.post(f'{URL}practice/', {'notebook_id': notebook.id, 'key': key}, format='json')

    assert first.status_code == 200, first.json()
    ids = first.json()['card_ids']
    assert len(ids) == 2 and second.json()['card_ids'] == ids
    cards = Flashcard.objects.filter(id__in=ids)
    assert all(c.user == user and c.notebook_id == notebook.id and not c.archived for c in cards)
    assert {c.question for c in cards} == {c['question'] for c in FOUND['misconceptions'][0]['cards']}
    # Tied to the document the mix-up came from, so the study page can scope them.
    assert all(list(c.sources.values_list('id', flat=True)) == [notebook.sources.first().id] for c in cards)


def test_an_unknown_misconception_cannot_make_cards(client, user, notebook, finder):
    _sat(user, notebook)
    _listed(client)

    res = client.post(f'{URL}practice/', {'notebook_id': notebook.id, 'key': 'nope'}, format='json')

    assert res.status_code == 404


def test_the_page_never_waits_for_the_model(client, user, notebook, finder, settings):
    # A model can hold a request for minutes. Asked for the first time, the
    # page answers at once that the finding is on its way, and the request
    # runs on its own; the next look shows the result.
    from quizzes.services import misconceptions as mc
    settings.MISCONCEPTIONS_IN_BACKGROUND = True
    _sat(user, notebook)

    first = client.get(URL).json()
    mc.wait_for_background()
    second = client.get(URL).json()

    assert first['pending'] is True and first['notebooks'] == []
    assert second['pending'] is False and second['notebooks'][0]['items']
    assert len(finder.prompts) == 1


def test_the_same_mix_up_seen_both_ways_is_one_item(client, user, notebook, finder):
    # "Took an acid for a base" and "took a base for an acid" are one confusion.
    a = dict(FOUND['misconceptions'][0], confused='Acids', answers=[1, 2],
             **{'with': 'Bases'}, cards=[{'question': 'Acid or base: pH 2?', 'answer': 'Acid'}])
    b = dict(FOUND['misconceptions'][0], confused='Bases', answers=[3, 4],
             **{'with': 'Acids'}, cards=[{'question': 'Acid or base: pH 12?', 'answer': 'Base'}])
    finder.reply = {'misconceptions': [a, b]}
    _sat(user, notebook)

    items = _listed(client)[0]['items']

    assert len(items) == 1
    assert {items[0]['confused'], items[0]['with']} == {'Acids', 'Bases'}
    assert items[0]['evidence'] == 4
