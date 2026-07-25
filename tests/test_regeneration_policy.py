"""Which flagged cards get regenerated on a given due-fetch."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "flashcards" / "services" / "regeneration.py")


def _load():
    spec = importlib.util.spec_from_file_location("regeneration_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load()
select_for_regeneration = _mod.select_for_regeneration
merge_replacements = _mod.merge_replacements


def _card(card_id, *, flagged, status="due"):
    return {"id": card_id, "needs_regeneration": flagged, "status": status}


def test_only_flagged_due_cards_are_selected():
    cards = [
        _card(1, flagged=True),
        _card(2, flagged=False),
        _card(3, flagged=True, status="new"),
    ]
    assert [c["id"] for c in select_for_regeneration(cards, limit=5)] == [1]


def test_selection_is_capped_so_one_fetch_cannot_stall():
    cards = [_card(i, flagged=True) for i in range(1, 11)]
    assert len(select_for_regeneration(cards, limit=3)) == 3


def test_nothing_flagged_means_no_work():
    assert select_for_regeneration([_card(1, flagged=False)], limit=5) == []


def test_merge_replacements_preserves_order():
    ranked = [{"id": 1}, {"id": 2}, {"id": 3}]
    replacements = {
        1: {"id": 1, "regenerated": True},
        3: {"id": 3, "regenerated": True},
    }
    merged = merge_replacements(ranked, replacements)
    assert [c["id"] for c in merged] == [1, 2, 3]
    assert merged[0] is replacements[1]
    assert merged[2] is replacements[3]


def test_merge_replacements_passes_through_entries_with_no_replacement():
    ranked = [{"id": 1}, {"id": 2}]
    merged = merge_replacements(ranked, {1: {"id": 1, "regenerated": True}})
    assert merged[1] is ranked[1]


def test_merge_replacements_with_empty_map_is_a_no_op():
    ranked = [{"id": 1}, {"id": 2}]
    assert merge_replacements(ranked, {}) == ranked
