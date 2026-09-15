"""Which items make up "the deck" for a selection of sources."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "notebooks" / "services" / "decks.py")


def _load():
    spec = importlib.util.spec_from_file_location("decks_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


decks = _load()

# (item_id, source_id) pairs, as the through table would hand them over.
PAIRS = [
    (1, 9),            # card 1: [9]
    (2, 9), (2, 11),   # card 2: [9, 11]
    (3, 11),           # card 3: [11]
    (4, 9),            # card 4: [9]
]


def test_exact_set_matches_only_items_with_those_sources_and_no_others():
    assert sorted(decks.items_with_exact_sources(PAIRS, [9])) == [1, 4]


def test_a_superset_is_not_the_same_deck():
    # Card 2 has 9 as well, but it was generated from 9 and 11 together.
    assert 2 not in decks.items_with_exact_sources(PAIRS, [9])


def test_selection_order_does_not_matter():
    assert decks.items_with_exact_sources(PAIRS, [11, 9]) == [2]


def test_empty_selection_matches_nothing():
    assert decks.items_with_exact_sources(PAIRS, []) == []
