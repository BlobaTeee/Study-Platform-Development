"""How large one flashcard generation is."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "notebooks" / "services" / "deck_limits.py")


def _load():
    spec = importlib.util.spec_from_file_location("deck_limits_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load()
MAX_CARDS_PER_SOURCE = _mod.MAX_CARDS_PER_SOURCE
MIN_CARDS_PER_SOURCE = _mod.MIN_CARDS_PER_SOURCE
batch_size = _mod.batch_size


def test_a_generation_is_ten_cards():
    assert MAX_CARDS_PER_SOURCE == 10


def test_the_default_request_is_honoured_whole():
    assert batch_size(10) == 10


def test_an_oversized_request_is_cut_to_the_maximum():
    assert batch_size(50) == MAX_CARDS_PER_SOURCE


def test_a_request_under_the_floor_is_raised():
    # A two-card deck is not worth a study session.
    assert batch_size(1) == MIN_CARDS_PER_SOURCE


def test_a_request_between_the_bounds_is_left_alone():
    assert batch_size(6) == 6


def test_nonsense_requests_still_produce_a_studiable_deck():
    # A malformed or missing count must not ask a generator for nothing: an
    # empty result reads downstream as a failed generation.
    assert batch_size(0) == MIN_CARDS_PER_SOURCE
    assert batch_size(-7) == MIN_CARDS_PER_SOURCE


def test_the_maximum_wins_when_it_falls_below_the_floor():
    # Guards the clamp order: a caller passing a maximum under the floor must
    # get that maximum, not a batch larger than the ceiling they asked for.
    assert batch_size(10, maximum=2) == 2
