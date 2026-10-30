"""Building the map by hand: link concepts, say why, get it graded.

A round is about six concepts around the weakest. The student's links are
graded in one model request; the document's links they did not make come
from the stored map, with no request. A correct link counts as
understanding both concepts on the map, a wrong one against, partial neither.
"""
import pytest

from notebooks.models import MapBuild, Notebook
from notebooks.services.knowledge_map import concepts_hash, concepts_of
from tests.conftest import make_source

pytestmark = pytest.mark.django_db
BUILD = '/api/notebooks/notebooks/{}/map/build/'
SUBMIT = '/api/notebooks/notebooks/{}/map/build/{}/submit/'
MAP = '/api/notebooks/notebooks/{}/map/'

POINTS = [
    ('Mitosis', 'Mitosis splits one nucleus into two identical nuclei.'),
    ('Chromosomes', 'Chromosomes carry tightly coiled DNA strands inside the nucleus.'),
    ('Cell cycle', 'The cell cycle runs through interphase growth before division.'),
    ('Photosynthesis', 'Chloroplasts capture sunlight to make glucose from carbon dioxide.'),
    ('Enzymes', 'Enzymes are proteins lowering activation energy of reactions.'),
]


class Provider:
    """Answers the grading prompt with the verdicts given; counts requests."""
    name = 'fake'

    def __init__(self, verdicts=None, fail=False):
        self.verdicts, self.fail, self.calls = verdicts or [], fail, 0

    def generate_json(self, prompt):
        self.calls += 1
        if self.fail:
            raise RuntimeError('model down')
        if 'cannot be understood without' in prompt:          # the document's own links
            return {'links': [{'before': 1, 'after': 2, 'why': 'Mitosis moves chromosomes.'}]}
        return {'links': [{'n': i + 1, 'verdict': v, 'feedback': f'note {i + 1}'} for i, v in enumerate(self.verdicts)]}


@pytest.fixture
def ai(monkeypatch):
    def use(**kw):
        p = Provider(**kw)
        monkeypatch.setattr('notebooks.services.map_building.get_ai_provider', lambda: p)
        monkeypatch.setattr('notebooks.services.knowledge_map.get_ai_provider', lambda: p)
        return p
    return use


@pytest.fixture
def biology(user):
    nb = Notebook.objects.create(user=user, title='Biology')
    src = make_source(nb, 'Cells', ' '.join(p for _, p in POINTS) * 20)
    src.key_points = [{'label': label, 'point': label, 'importance': 'core', 'passage': passage}
                      for label, passage in POINTS]
    src.save()
    concepts = concepts_of(nb)
    key = {c['label']: c['key'] for c in concepts}
    nb.concept_links = {'hash': concepts_hash(concepts), 'edges': [
        {'from': key['Chromosomes'], 'to': key['Mitosis'], 'why': 'Mitosis separates the copied chromosomes.'},
        {'from': key['Cell cycle'], 'to': key['Mitosis'], 'why': 'Mitosis is the division phase of the cycle.'},
    ]}
    nb.save()
    return nb, key


def _start(client, nb):
    return client.post(BUILD.format(nb.id), {}, format='json')


def _submit(client, nb, build_id, links):
    return client.post(SUBMIT.format(nb.id, build_id), {'links': links}, format='json')


def test_a_round_offers_the_concepts_without_their_links(client, biology, ai):
    nb, key = biology
    ai()
    res = _start(client, nb)
    assert res.status_code == 201
    body = res.json()
    assert {c['label'] for c in body['concepts']} == {label for label, _ in POINTS}
    assert 'edges' not in body and 'why' not in str(body)
    assert MapBuild.objects.get(pk=body['id']).graded_at is None


def test_a_notebook_with_too_few_concepts_cannot_start(client, user, ai):
    ai()
    nb = Notebook.objects.create(user=user, title='Thin')
    src = make_source(nb, 'One')
    src.key_points = [{'label': 'Only', 'point': 'Only one idea here', 'importance': 'core', 'passage': 'x'}]
    src.save()
    res = _start(client, nb)
    assert res.status_code == 400 and res.json()['too_few'] is True


def test_the_documents_links_are_found_first_when_missing(client, biology, ai):
    nb, _ = biology
    nb.concept_links = {}
    nb.save()
    p = ai()
    assert _start(client, nb).status_code == 201
    assert p.calls == 1 and Notebook.objects.get(pk=nb.pk).concept_links.get('edges')


def test_a_stranger_cannot_build_on_someone_elses_notebook(other_client, biology, ai):
    ai()
    assert _start(other_client, biology[0]).status_code == 404


def test_links_are_checked_before_any_request(client, biology, ai):
    nb, key = biology
    p = ai(verdicts=['correct'])
    build = _start(client, nb).json()['id']
    why = 'Because one depends on the other.'
    bad = [
        [],                                                                       # nothing linked
        [{'from': key['Mitosis'], 'to': key['Mitosis'], 'why': why}],             # to itself
        [{'from': key['Mitosis'], 'to': 'nope', 'why': why}],                     # not in the round
        [{'from': key['Mitosis'], 'to': key['Chromosomes'], 'why': ''}],          # no reason
        [{'from': key['Mitosis'], 'to': key['Chromosomes'], 'why': why},
         {'from': key['Chromosomes'], 'to': key['Mitosis'], 'why': why}],         # the same pair twice
    ]
    for links in bad:
        assert _submit(client, nb, build, links).status_code == 400, links
    assert p.calls == 0


def test_a_round_is_graded_in_one_request_with_the_missed_links(client, biology, ai):
    nb, key = biology
    p = ai(verdicts=['correct', 'wrong'])
    build = _start(client, nb).json()['id']
    res = _submit(client, nb, build, [
        {'from': key['Mitosis'], 'to': key['Chromosomes'], 'why': 'Mitosis splits the copied chromosomes evenly.'},
        {'from': key['Enzymes'], 'to': key['Photosynthesis'], 'why': 'Enzymes are made by photosynthesis.'},
    ])
    assert res.status_code == 200 and p.calls == 1
    body = res.json()
    assert [(link['verdict'], link['feedback']) for link in body['links']] == [('correct', 'Note 1'), ('wrong', 'Note 2')]  # tidied: a sentence starts upper case
    # Chromosomes-Mitosis was made (in the other direction); Cell cycle-Mitosis was not.
    assert [(m['from'], m['to']) for m in body['missed']] == [(key['Cell cycle'], key['Mitosis'])]
    assert body['missed'][0]['why'] == 'Mitosis is the division phase of the cycle.'


def test_a_round_is_graded_once(client, biology, ai):
    nb, key = biology
    ai(verdicts=['correct'])
    build = _start(client, nb).json()['id']
    link = [{'from': key['Mitosis'], 'to': key['Chromosomes'], 'why': 'Mitosis splits the chromosomes.'}]
    assert _submit(client, nb, build, link).status_code == 200
    assert _submit(client, nb, build, link).status_code == 409


def test_a_failed_grading_can_be_sent_again(client, biology, ai):
    nb, key = biology
    ai(fail=True)
    build = _start(client, nb).json()['id']
    link = [{'from': key['Mitosis'], 'to': key['Chromosomes'], 'why': 'Mitosis splits the chromosomes.'}]
    assert _submit(client, nb, build, link).status_code == 503
    ai(verdicts=['correct'])
    assert _submit(client, nb, build, link).status_code == 200


def test_a_link_the_model_left_out_is_not_counted(client, biology, ai):
    nb, key = biology
    ai(verdicts=['correct'])                       # one verdict for two links
    build = _start(client, nb).json()['id']
    body = _submit(client, nb, build, [
        {'from': key['Mitosis'], 'to': key['Chromosomes'], 'why': 'Mitosis splits the chromosomes.'},
        {'from': key['Enzymes'], 'to': key['Photosynthesis'], 'why': 'Both happen inside plant cells.'},
    ]).json()
    assert [link['verdict'] for link in body['links']] == ['correct', 'unjudged']


def test_graded_links_count_on_the_map_and_partial_does_not(client, biology, ai):
    nb, key = biology
    ai(verdicts=['correct', 'partial', 'wrong'])
    build = _start(client, nb).json()['id']
    _submit(client, nb, build, [
        {'from': key['Mitosis'], 'to': key['Chromosomes'], 'why': 'Mitosis splits the copied chromosomes.'},
        {'from': key['Cell cycle'], 'to': key['Enzymes'], 'why': 'Enzymes run the steps of the cycle.'},
        {'from': key['Photosynthesis'], 'to': key['Mitosis'], 'why': 'Photosynthesis powers mitosis.'},
    ])
    by_label = {c['label']: c for c in client.get(MAP.format(nb.id)).json()['concepts']}
    assert by_label['Chromosomes']['understanding'] == {**by_label['Chromosomes']['understanding'], 'correct': 1, 'total': 1}
    assert by_label['Mitosis']['understanding']['correct'] == 1 and by_label['Mitosis']['understanding']['total'] == 2
    assert by_label['Photosynthesis']['understanding']['correct'] == 0
    assert by_label['Enzymes']['understanding'] is None              # only a partial link
