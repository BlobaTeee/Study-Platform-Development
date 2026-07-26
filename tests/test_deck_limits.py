"""How much room a document has left for new flashcards."""
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
room_for = _mod.room_for
capped_count = _mod.capped_count


def test_an_empty_document_has_room_for_the_whole_cap():
    assert room_for(0) == MAX_CARDS_PER_SOURCE


def test_a_partly_filled_document_tops_up():
    assert room_for(6) == 4


def test_a_full_document_has_no_room():
    assert room_for(MAX_CARDS_PER_SOURCE) == 0


def test_room_never_goes_negative():
    # Documents generated before the cap existed can exceed it; they must not
    # produce a negative request that would read as "unlimited" downstream.
    assert room_for(25) == 0


def test_the_cap_is_ten():
    assert MAX_CARDS_PER_SOURCE == 10


def test_capped_count_shrinks_a_top_up_request_to_the_remaining_room():
    # 9 active cards, 10 requested (the max(3, ...) clamp's usual output) -> 1,
    # not 10 and not the clamp's floor of 3.
    assert capped_count(10, 9) == 1


def test_capped_count_leaves_a_fresh_request_untouched():
    assert capped_count(10, 0) == 10


def test_capped_count_on_a_full_document_is_zero():
    assert capped_count(10, MAX_CARDS_PER_SOURCE) == 0


def test_capped_count_never_goes_negative_past_the_cap():
    assert capped_count(10, 25) == 0


def test_capped_count_returns_small_requests_unchanged():
    # Requesting fewer than the remaining room should not be inflated.
    assert capped_count(2, 3) == 2
