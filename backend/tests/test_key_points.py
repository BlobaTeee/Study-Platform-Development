"""Ý chính của tài liệu: AI đọc cả tài liệu một lần rồi rút ra các ý chính.

Questions used to come from three passages picked by word statistics out of
the first 18,000 characters, so most of a long document was never asked
about and the picks followed keyword density, not importance. Now the model
reads the whole document once and lists its main ideas, core first, each
with a quote from the text as evidence. A quote that is not in the
document means the idea was not either, so it is dropped. The list is kept
on the source: an upload gets it in the request that already writes the
overview, and an older document gets it the first time it is needed.
"""
import pytest

from notebooks.models import Source
from notebooks.services.key_points import MAX_READ_CHARS, ensure_key_points, read_document
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

INTRO = 'Mobile phones are a lifeline for homeless young people. '
FILLER = 'This sentence only fills space in the middle of the lecture. ' * 400
ENDING = 'Depleted batteries undermine the safety a phone provides. '
DOC = INTRO * 3 + FILLER + ENDING * 3      # the ending sits past 18,000 characters


class _Reader:
    name = 'stub'

    def __init__(self, points=None, fail=False):
        self.prompts = []
        self.fail = fail
        self.points = points if points is not None else [
            {'point': 'Phones are a lifeline for homeless youth.', 'importance': 'core',
             'quote': 'Mobile phones are a lifeline for homeless young people.'},
            {'point': 'Flat batteries cancel that safety.', 'importance': 'supporting',
             'quote': 'Depleted batteries undermine the safety a phone provides.'},
        ]

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError('provider down')
        return {'summary': 'Phones keep homeless youth safe until they fail.', 'key_points': self.points}

    def summarize(self, text, title=''):
        return ''


@pytest.fixture
def reader(monkeypatch):
    r = _Reader()
    monkeypatch.setattr('notebooks.services.key_points.get_ai_provider', lambda: r)
    return r


def test_the_whole_document_is_read(reader):
    assert len(DOC) > 18000
    read_document(DOC, 'Lecture')

    assert ENDING.strip() in reader.prompts[-1]


def test_a_very_long_document_is_read_up_to_the_cap(reader):
    read_document('x' * (MAX_READ_CHARS + 5000), 'Long')
    assert 'x' * MAX_READ_CHARS in reader.prompts[-1]
    assert 'x' * (MAX_READ_CHARS + 1) not in reader.prompts[-1]


def test_points_come_core_first_with_their_passage(reader):
    reader.points = list(reversed(reader.points))
    points = read_document(DOC, 'Lecture')['key_points']

    assert [p['importance'] for p in points] == ['core', 'supporting']
    assert points[0]['point'] == 'Phones are a lifeline for homeless youth.'
    assert 'Mobile phones are a lifeline' in points[0]['passage']
    assert 'Depleted batteries' in points[1]['passage']


def test_a_point_whose_quote_is_not_in_the_document_is_dropped(reader):
    reader.points = reader.points + [{'point': 'Phones cure illness.', 'importance': 'core',
                                      'quote': 'Smartphones cure every known disease overnight.'}]
    points = read_document(DOC, 'Lecture')['key_points']

    assert 'Phones cure illness.' not in [p['point'] for p in points]


def test_small_differences_in_a_quote_still_find_it(reader):
    # Models straighten quotes and change spacing when copying.
    reader.points = [{'point': 'Phones are a lifeline.', 'importance': 'core',
                      'quote': '  mobile phones are a LIFELINE for homeless young people'}]
    assert len(read_document(DOC, 'Lecture')['key_points']) == 1


def test_the_summary_comes_from_the_same_request(reader):
    out = read_document(DOC, 'Lecture')

    assert out['summary'] == 'Phones keep homeless youth safe until they fail.'
    assert len(reader.prompts) == 1


def test_an_older_document_gets_its_points_once(user, notebook, reader):
    source = make_source(notebook, 'Lecture', DOC)

    first = ensure_key_points(source)
    second = ensure_key_points(Source.objects.get(id=source.id))

    assert first and first == second
    assert len(reader.prompts) == 1


def test_without_a_provider_there_are_no_points_and_nothing_is_kept(user, notebook, monkeypatch):
    monkeypatch.setattr('notebooks.services.key_points.get_ai_provider', lambda: _Reader(fail=True))
    source = make_source(notebook, 'Lecture', DOC)

    assert ensure_key_points(source) == []
    assert Source.objects.get(id=source.id).key_points == []


def test_an_upload_gets_points_and_overview_in_one_request(client, notebook, monkeypatch):
    r = _Reader()
    monkeypatch.setattr('notebooks.services.key_points.get_ai_provider', lambda: r)
    res = client.post(f'/api/notebooks/notebooks/{notebook.id}/add_text/',
                      {'text': DOC, 'title': 'Lecture'}, format='json')
    assert res.status_code in (200, 201), res.json()

    source = Source.objects.get(id=res.json()['id'])
    assert len(source.key_points) == 2
    assert source.gemini_summary.startswith('Phones keep')
    assert len(r.prompts) == 1


def test_the_points_are_served_with_the_document(client, user, notebook, reader):
    source = make_source(notebook, 'Lecture', DOC)
    ensure_key_points(source)

    body = client.get(f'/api/notebooks/sources/{source.id}/').json()

    assert body['key_points'][0]['point'] == 'Phones are a lifeline for homeless youth.'
    assert body['key_points'][0]['importance'] == 'core'


def test_an_older_document_can_be_read_on_request(client, user, notebook, reader):
    source = make_source(notebook, 'Lecture', DOC)

    res = client.post(f'/api/notebooks/sources/{source.id}/read/')

    assert res.status_code == 200, res.json()
    assert res.json()['key_points'][0]['importance'] == 'core'
    assert len(reader.prompts) == 1
    client.post(f'/api/notebooks/sources/{source.id}/read/')
    assert len(reader.prompts) == 1          # read once, then kept


def test_reading_on_request_says_so_when_it_cannot(client, user, notebook, monkeypatch):
    monkeypatch.setattr('notebooks.services.key_points.get_ai_provider', lambda: _Reader(fail=True))
    source = make_source(notebook, 'Lecture', DOC)

    res = client.post(f'/api/notebooks/sources/{source.id}/read/')

    assert res.status_code == 503
    assert res.json()['detail']


def test_each_point_has_a_short_label_for_the_reader(reader):
    reader.points = [dict(reader.points[0], label='Phones as a lifeline'),
                     dict(reader.points[1], label='Flat batteries')]
    points = read_document(DOC, 'Lecture')['key_points']

    assert [p['label'] for p in points] == ['Phones as a lifeline', 'Flat batteries']
    assert '"label"' in reader.prompts[-1]


def test_a_missing_or_long_label_falls_back_to_nothing(reader):
    reader.points = [dict(reader.points[0], label='one ' * 30), dict(reader.points[1])]
    points = read_document(DOC, 'Lecture')['key_points']

    assert all(p['label'] == '' for p in points)
