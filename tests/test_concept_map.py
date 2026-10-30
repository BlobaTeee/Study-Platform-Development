"""The knowledge map's logic: concepts, attachment, links, state, action."""
from ml_pipeline.concept_map import (
    attach, choose_action, clean_links, concept_state, merge_concepts, weaker,
)

T = {'strong': 0.8, 'shaky': 0.5}


def kp(key, source_id, label, passage):
    return {'key': key, 'source_id': source_id, 'label': label, 'point': label, 'passage': passage,
            'importance': 'core'}


def test_the_same_idea_in_two_documents_is_one_concept():
    concepts = merge_concepts([
        kp('1:0', 1, 'Covalent bonding', 'Atoms share pairs of electrons in a covalent bond.'),
        kp('2:3', 2, 'Covalent bonds', 'A covalent bond forms when two atoms share a pair of electrons.'),
        kp('1:1', 1, 'Acids and bases', 'Acids donate protons; bases accept protons.'),
    ])
    assert [c['members'] for c in concepts] == [['1:0', '2:3'], ['1:1']]
    assert concepts[0]['source_ids'] == [1, 2]


def test_two_ideas_in_one_document_are_never_merged():
    concepts = merge_concepts([kp('1:0', 1, 'Covalent bonding', 'Atoms share electrons.'),
                               kp('1:1', 1, 'Covalent bonding', 'Atoms share electrons.')])
    assert len(concepts) == 2


def test_an_item_goes_to_its_closest_concept_among_its_own_sources():
    concepts = merge_concepts([kp('1:0', 1, 'Acids', 'An acid donates a proton to a base in water.'),
                               kp('1:1', 1, 'Enzymes', 'Enzymes are proteins that speed up reactions.'),
                               kp('2:0', 2, 'Acids', 'An acid donates a proton.')])
    got = attach([{'id': 'card:5', 'text': 'What does an acid donate? A proton', 'source_ids': [1]},
                  {'id': 'q:9', 'text': 'Which molecules speed reactions? Enzymes', 'source_ids': [1]},
                  {'id': 'q:10', 'text': 'Photosynthesis in leaves', 'source_ids': [1]}], concepts)
    assert got['card:5'] == concepts[0]['key'] and got['q:9'] == concepts[1]['key']
    assert got['q:10'] is None


def test_links_keep_known_pairs_drop_self_unknown_and_loops():
    raw = [{'before': 1, 'after': 2, 'why': 'a'}, {'before': 2, 'after': 3, 'why': 'b'},
           {'before': 3, 'after': 1, 'why': 'loop'}, {'before': 2, 'after': 2, 'why': 'self'},
           {'before': 9, 'after': 1, 'why': 'unknown'}, 'junk', {'before': '1', 'after': 3}]
    assert clean_links(raw, 3) == [(0, 1, 'a'), (1, 2, 'b')]


def test_a_concept_keeps_at_most_three_prerequisites():
    raw = [{'before': i, 'after': 5, 'why': str(i)} for i in (1, 2, 3, 4)]
    assert len(clean_links(raw, 5)) == 3


def test_state_is_the_weaker_signal_and_none_means_not_studied():
    assert concept_state(0.9, 0.3, T) == 'weak'
    assert concept_state(0.9, None, T) == 'strong'
    assert concept_state(None, 0.6, T) == 'shaky'
    assert concept_state(None, None, T) == 'not_studied'
    assert weaker(0.9, 0.3) == 'memory' and weaker(0.4, 0.9) == 'understanding' and weaker(None, None) is None


def test_the_action_follows_the_weaker_side():
    assert choose_action('memory', [3, 4], [], [7]) == {'kind': 'cards', 'card_ids': [3, 4]}
    assert choose_action('understanding', [3], [11], [7]) == {'kind': 'exercise', 'exercise_id': 11}
    assert choose_action('understanding', [3], [], [7, 8]) == {'kind': 'practice', 'question_ids': [7, 8]}
    assert choose_action('understanding', [3], [], []) == {'kind': 'cards', 'card_ids': [3]}


def test_a_concept_never_studied_starts_with_its_cards_or_nothing():
    assert choose_action(None, [3], [], [7]) == {'kind': 'cards', 'card_ids': [3]}
    assert choose_action(None, [], [], []) is None


# ---- choosing a round to build by hand ------------------------------------------

def c(key, state='strong'):
    return {'key': key, 'state': state}


def e(a, b):
    return {'from': a, 'to': b}


def test_a_round_starts_at_the_weakest_and_follows_its_links():
    from ml_pipeline.concept_map import pick_round
    concepts = [c('a'), c('b', 'shaky'), c('c'), c('d', 'weak'), c('e'), c('f'), c('g'), c('h')]
    edges = [e('d', 'c'), e('c', 'e'), e('a', 'b'), e('g', 'h')]
    picked = pick_round(concepts, edges, size=3)
    assert picked[0] == 'd'
    assert set(picked) == {'d', 'c', 'e'}          # d's neighbourhood, not the shaky b far away


def test_when_the_links_run_out_the_weakest_others_fill_the_round():
    from ml_pipeline.concept_map import pick_round
    concepts = [c('a'), c('b', 'not_studied'), c('c', 'weak'), c('d', 'shaky'), c('e')]
    picked = pick_round(concepts, [], size=3)
    assert picked == ['c', 'd', 'b']


def test_a_small_notebook_uses_every_concept():
    from ml_pipeline.concept_map import pick_round
    concepts = [c('a'), c('b'), c('c')]
    assert sorted(pick_round(concepts, [e('a', 'b')], size=6)) == ['a', 'b', 'c']


def test_links_count_both_ways_when_walking_out():
    from ml_pipeline.concept_map import pick_round
    concepts = [c('a'), c('b', 'weak'), c('c'), c('d')]
    assert set(pick_round(concepts, [e('a', 'b')], size=2)) == {'a', 'b'}
