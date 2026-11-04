"""Building a map yourself: write the concepts from memory, link them, say why.

The student picks one document, writes the concepts they remember as cards
and links them with a reason. One model request compares that with the
document's key points: which card matches which point, and a verdict on
each link. The document's own links between recalled concepts that the
student did not join come from the stored map, with no request. A link
counts on the map for the concepts its cards match.
"""
import pytest

from notebooks.models import MapBuild, Notebook
from notebooks.services.knowledge_map import concepts_hash, concepts_of
from tests.conftest import make_source

pytestmark = pytest.mark.django_db
BUILD = '/api/notebooks/notebooks/{}/map/build/'
TOPICS = '/api/notebooks/notebooks/{}/map/topics/'
MAP = '/api/notebooks/notebooks/{}/map/'

POINTS = [
    ('Mitosis', 'Mitosis splits one nucleus into two identical nuclei.'),
    ('Chromosomes', 'Chromosomes carry tightly coiled DNA strands inside the nucleus.'),
    ('Cell cycle', 'The cell cycle runs through interphase growth before division.'),
    ('Photosynthesis', 'Chloroplasts capture sunlight to make glucose from carbon dioxide.'),
    ('Enzymes', 'Enzymes are proteins lowering activation energy of reactions.'),
]


class Provider:
    """Answers the comparison with the matches and verdicts given; counts requests."""
    name = 'fake'

    def __init__(self, matches=None, verdicts=None, fail=False):
        self.matches, self.verdicts, self.fail, self.calls, self.prompt = matches or {}, verdicts or [], fail, 0, ''

    def generate_json(self, prompt):
        self.calls += 1
        self.prompt = prompt
        if self.fail:
            raise RuntimeError('model down')
        return {'cards': [{'n': n, 'matches': m} for n, m in self.matches.items()],
                'links': [{'n': i + 1, 'verdict': v, 'feedback': f'note {i + 1}'} for i, v in enumerate(self.verdicts)]}


@pytest.fixture
def ai(monkeypatch):
    def use(**kw):
        p = Provider(**kw)
        monkeypatch.setattr('notebooks.services.map_building.get_ai_provider', lambda: p)
        return p
    return use


@pytest.fixture
def biology(user):
    nb = Notebook.objects.create(user=user, title='Biology')
    src = make_source(nb, 'Cells', ' '.join(p for _, p in POINTS) * 20)
    src.key_points = [{'label': label, 'point': passage, 'importance': 'core', 'passage': passage}
                      for label, passage in POINTS]
    src.save()
    concepts = concepts_of(nb)
    key = {c['label']: c['key'] for c in concepts}
    nb.concept_links = {'hash': concepts_hash(concepts), 'edges': [
        {'from': key['Chromosomes'], 'to': key['Mitosis'], 'why': 'Mitosis separates the copied chromosomes.'},
        {'from': key['Cell cycle'], 'to': key['Mitosis'], 'why': 'Mitosis is the division phase of the cycle.'},
    ]}
    nb.save()
    return nb, src, key


CARDS = [{'id': 'a', 'label': 'Nguyên phân'}, {'id': 'b', 'label': 'Nhiễm sắc thể'},
         {'id': 'c', 'label': 'Chu kỳ tế bào'}, {'id': 'd', 'label': 'Ribosome'}]
WHY = 'Trong nguyên phân, nhiễm sắc thể nhân đôi rồi chia đều về hai tế bào con.'


def _send(client, nb, src, cards=CARDS, links=None):
    links = links if links is not None else [{'from': 'a', 'to': 'b', 'why': WHY}]
    return client.post(BUILD.format(nb.id), {'source': src.id, 'cards': cards, 'links': links}, format='json')


def test_the_topics_are_documents_with_enough_key_points(client, biology, user):
    nb, src, _ = biology
    thin = make_source(nb, 'Notes')
    thin.key_points = [{'label': 'One', 'point': 'Only one idea', 'importance': 'core', 'passage': 'x'}]
    thin.save()
    topics = client.get(TOPICS.format(nb.id)).json()['topics']
    assert topics == [{'source_id': src.id, 'title': 'Cells', 'key_points': 5}]
    assert 'Mitosis' not in str(topics)                  # the title only: no hints


def test_a_stranger_cannot_build_on_someone_elses_notebook(other_client, biology, ai):
    nb, src, _ = biology
    ai()
    assert other_client.get(TOPICS.format(nb.id)).status_code == 404
    assert _send(other_client, nb, src).status_code == 404


def test_cards_and_links_are_checked_before_any_request(client, biology, ai):
    nb, src, _ = biology
    p = ai(verdicts=['correct'])
    two = CARDS[:2]
    bad = [
        dict(cards=two),                                                        # too few cards
        dict(cards=CARDS + [{'id': 'e', 'label': 'nguyên PHÂN'}]),              # the same label twice
        dict(cards=CARDS[:3] + [{'id': 'd', 'label': ''}]),                    # an empty card
        dict(links=[]),                                                         # nothing linked
        dict(links=[{'from': 'a', 'to': 'a', 'why': WHY}]),                     # to itself
        dict(links=[{'from': 'a', 'to': 'zz', 'why': WHY}]),                    # not one of the cards
        dict(links=[{'from': 'a', 'to': 'b', 'why': ''}]),                      # no reason
        dict(links=[{'from': 'a', 'to': 'b', 'why': WHY}, {'from': 'b', 'to': 'a', 'why': WHY}]),  # twice
    ]
    for case in bad:
        assert _send(client, nb, src, **case).status_code == 400, case
    assert p.calls == 0 and not MapBuild.objects.exists()


def test_a_document_without_enough_key_points_is_not_a_topic(client, biology, ai):
    nb, _, _ = biology
    ai()
    thin = make_source(nb, 'Notes')
    assert _send(client, nb, thin).status_code == 400


def test_one_request_compares_the_map_with_the_document(client, biology, ai):
    nb, src, key = biology
    # a = Mitosis (1), b = Chromosomes (2), c = Cell cycle (3); d (Ribosome) is in no key point.
    p = ai(matches={1: 1, 2: 2, 3: 3, 4: None}, verdicts=['correct', 'wrong'])
    res = _send(client, nb, src, links=[
        {'from': 'a', 'to': 'b', 'why': WHY},
        {'from': 'c', 'to': 'd', 'why': 'Ribosome điều khiển chu kỳ tế bào.'},
    ])
    assert res.status_code == 201 and p.calls == 1
    body = res.json()
    assert body['recalled'] == 3 and body['total'] == 5
    assert [m['label'] for m in body['missed_points']] == ['Photosynthesis', 'Enzymes']
    assert [(c['id'], c['match_label']) for c in body['cards']] == [
        ('a', 'Mitosis'), ('b', 'Chromosomes'), ('c', 'Cell cycle'), ('d', None)]
    assert [(link['verdict'], link['feedback']) for link in body['links']] == [('correct', 'Note 1'), ('wrong', 'Note 2')]
    # Chromosomes-Mitosis was joined; Cell cycle-Mitosis, both recalled, was not.
    assert [(m['from'], m['to']) for m in body['missed']] == [('c', 'a')]
    assert body['missed'][0]['why'] == 'Mitosis is the division phase of the cycle.'
    assert 'Mitosis splits one nucleus' in p.prompt and 'Nguyên phân' in p.prompt


def test_nothing_is_kept_when_grading_fails_so_it_can_be_sent_again(client, biology, ai):
    nb, src, _ = biology
    ai(fail=True)
    assert _send(client, nb, src).status_code == 503
    assert not MapBuild.objects.exists()
    ai(matches={1: 1, 2: 2}, verdicts=['correct'])
    assert _send(client, nb, src).status_code == 201


def test_a_link_or_card_the_model_left_out_is_not_counted(client, biology, ai):
    nb, src, _ = biology
    ai(matches={1: 1, 2: 99}, verdicts=[])                 # card 2's match is no key point
    body = _send(client, nb, src).json()
    assert body['cards'][1]['match_label'] is None
    assert [link['verdict'] for link in body['links']] == ['unjudged']


def test_feedback_is_in_the_language_the_student_wrote_in(client, biology, ai):
    nb, src, _ = biology
    p = ai(matches={1: 1, 2: 2}, verdicts=['correct'])
    _send(client, nb, src)
    assert 'in Vietnamese' in p.prompt


def test_links_count_on_the_map_for_the_concepts_their_cards_match(client, biology, ai):
    nb, src, key = biology
    ai(matches={1: 1, 2: 2, 3: 3, 4: None}, verdicts=['correct', 'partial', 'wrong'])
    _send(client, nb, src, links=[
        {'from': 'a', 'to': 'b', 'why': WHY},
        {'from': 'c', 'to': 'b', 'why': 'Chu kỳ tế bào có liên quan tới nhiễm sắc thể.'},
        {'from': 'd', 'to': 'a', 'why': 'Ribosome tạo ra nhân mới.'},
    ])
    by_label = {c['label']: c for c in client.get(MAP.format(nb.id)).json()['concepts']}
    assert (by_label['Chromosomes']['understanding']['correct'], by_label['Chromosomes']['understanding']['total']) == (1, 1)
    assert (by_label['Mitosis']['understanding']['correct'], by_label['Mitosis']['understanding']['total']) == (1, 2)
    assert by_label['Cell cycle']['understanding'] is None          # only a partial link
    assert by_label['Enzymes']['understanding'] is None
