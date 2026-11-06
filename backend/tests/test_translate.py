"""Reading a document's content in the page language.

A document keeps its own language: its key points, summary and map reasons
are written in it. When the page is in the other language, the page asks
for those texts translated. A model on this machine translates each text
once; the result is kept, so the same text costs nothing the next time.
Texts already in the page language come back as they are.
"""
import pytest

from notebooks.models import Translation

pytestmark = pytest.mark.django_db
URL = '/api/notebooks/translate/'


class Machine:
    """Translates by tagging each text; counts calls and texts."""

    def __init__(self, fail=False):
        self.fail, self.calls, self.seen = fail, 0, []

    def __call__(self, texts, source, target):
        self.calls += 1
        self.seen += list(texts)
        if self.fail:
            raise RuntimeError('model missing')
        return [f'[{source}>{target}] {t}' for t in texts]


@pytest.fixture
def machine(monkeypatch):
    def use(**kw):
        m = Machine(**kw)
        monkeypatch.setattr('notebooks.services.translate.machine_translate', m)
        return m
    return use


EN = ['Energy conservation dictates that phase transitions must involve energy gain or loss.',
      'Phase Change Energy']


def test_english_texts_come_back_in_vietnamese_in_order(client, machine):
    m = machine()
    res = client.post(URL, {'texts': EN, 'to': 'vi'}, format='json')
    assert res.status_code == 200
    assert res.data == {'translations': [f'[en>vi] {t}' for t in EN], 'translated': True}
    assert m.calls == 1


def test_a_short_label_is_read_by_its_letters(client, machine):
    # A label alone has too few words to tell; Vietnamese marks say Vietnamese, none says English.
    machine()
    res = client.post(URL, {'texts': ['Phase Change Energy', 'Năng lượng chuyển pha'], 'to': 'vi'}, format='json')
    assert res.data['translations'] == ['[en>vi] Phase Change Energy', 'Năng lượng chuyển pha']
    res = client.post(URL, {'texts': ['Phase Change Energy', 'Năng lượng chuyển pha'], 'to': 'en'}, format='json')
    assert res.data['translations'] == ['Phase Change Energy', '[vi>en] Năng lượng chuyển pha']


def test_texts_already_in_the_page_language_are_left_alone(client, machine):
    m = machine()
    vi = 'Năng lượng được bảo toàn trong mọi quá trình chuyển pha của chất.'
    res = client.post(URL, {'texts': [vi, EN[0]], 'to': 'vi'}, format='json')
    assert res.data['translations'] == [vi, f'[en>vi] {EN[0]}']
    assert m.seen == [EN[0]]


def test_vietnamese_goes_to_english_too(client, machine):
    machine()
    vi = 'Năng lượng được bảo toàn trong mọi quá trình chuyển pha của chất.'
    res = client.post(URL, {'texts': [vi], 'to': 'en'}, format='json')
    assert res.data['translations'] == [f'[vi>en] {vi}']


def test_each_text_is_translated_once_then_kept(client, machine):
    m = machine()
    client.post(URL, {'texts': EN, 'to': 'vi'}, format='json')
    res = client.post(URL, {'texts': list(reversed(EN)), 'to': 'vi'}, format='json')
    assert res.data['translations'] == [f'[en>vi] {t}' for t in reversed(EN)]
    assert m.calls == 1
    assert Translation.objects.count() == 2


def test_repeated_texts_are_translated_once(client, machine):
    m = machine()
    res = client.post(URL, {'texts': [EN[0], EN[0]], 'to': 'vi'}, format='json')
    assert res.data['translations'] == [f'[en>vi] {EN[0]}'] * 2
    assert m.seen == [EN[0]]


def test_without_the_model_the_originals_come_back(client, machine):
    machine(fail=True)
    res = client.post(URL, {'texts': EN, 'to': 'vi'}, format='json')
    assert res.status_code == 200
    assert res.data == {'translations': EN, 'translated': False}
    assert Translation.objects.count() == 0


def test_blank_texts_and_other_languages_pass_through(client, machine):
    m = machine()
    res = client.post(URL, {'texts': ['', '  ', '能量守恒', '= 42'], 'to': 'vi'}, format='json')
    assert res.data['translations'] == ['', '  ', '能量守恒', '= 42']
    assert m.calls == 0


@pytest.mark.parametrize('body', [
    {'texts': 'not a list', 'to': 'vi'},
    {'texts': EN, 'to': 'fr'},
    {'texts': [1, 2], 'to': 'vi'},
    {'texts': ['x'] * 101, 'to': 'vi'},
    {'texts': ['x' * 3001], 'to': 'vi'},
])
def test_bad_requests_are_refused_before_any_translation(client, machine, body):
    m = machine()
    assert client.post(URL, body, format='json').status_code == 400
    assert m.calls == 0


def test_only_signed_in_students(machine):
    from rest_framework.test import APIClient
    assert APIClient(HTTP_HOST='localhost').post(URL, {'texts': EN, 'to': 'vi'}, format='json').status_code in (401, 403)
